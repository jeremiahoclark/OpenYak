"""Agent loop: the core processing engine."""

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from yak.bus.events import InboundMessage, MediaAttachment, OutboundMessage
from yak.bus.queue import MessageBus
from yak.providers.base import LLMProvider
from yak.agent.context import ContextBuilder
from yak.agent.tools.registry import ToolRegistry
from yak.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from yak.agent.tools.shell import ExecTool
from yak.agent.tools.web import WebSearchTool, WebFetchTool
from yak.agent.tools.message import MessageTool
from yak.agent.tools.spawn import SpawnTool
from yak.agent.tools.cron import CronTool
from yak.agent.tools.workflow_tools import TextToVideoWorkflowTool
from yak.agent.subagent import SubagentManager
from yak.session.manager import SessionManager
from yak.agent.tool_runtime import apply_tool_calls, extract_tool_calls_from_content
from yak.workflows.text_to_video import TextToVideoWorkflow


class AgentLoop:
    """
    The agent loop is the core processing engine.
    
    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """
    
    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        fallback_model: str | None = None,
        tool_failover_threshold: int = 3,
        calendar_client: "GoogleCalendarClient | None" = None,
    ):
        from yak.config.schema import ExecToolConfig
        from yak.cron.service import CronService
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self.fallback_model = fallback_model
        self.tool_failover_threshold = max(1, tool_failover_threshold)
        self.calendar_client = calendar_client
        self._consecutive_tool_failures = 0
        
        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.text_to_video_workflow = TextToVideoWorkflow()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )
        
        self._running = False
        self._register_default_tools()

    def _record_tool_results(self, tool_results: list[str]) -> None:
        """Track consecutive tool execution failures for model failover."""
        if not tool_results:
            self._consecutive_tool_failures = 0
            return
        for result in tool_results:
            if result.startswith("Error"):
                self._consecutive_tool_failures += 1
            else:
                self._consecutive_tool_failures = 0

    def _maybe_failover_model(self) -> None:
        """Switch to fallback model after repeated tool failures."""
        if not self.fallback_model or self.model == self.fallback_model:
            return
        if self._consecutive_tool_failures < self.tool_failover_threshold:
            return
        old_model = self.model
        self.model = self.fallback_model
        self._consecutive_tool_failures = 0
        logger.warning(
            f"Auto-switched model from {old_model} to {self.model} after "
            f"{self.tool_failover_threshold} consecutive tool failures"
        )
    
    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        # File tools (restrict to workspace if configured)
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        self.tools.register(ReadFileTool(allowed_dir=allowed_dir))
        self.tools.register(WriteFileTool(allowed_dir=allowed_dir))
        self.tools.register(EditFileTool(allowed_dir=allowed_dir))
        self.tools.register(ListDirTool(allowed_dir=allowed_dir))
        
        # Shell tool
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
        ))
        
        # Web tools
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())
        
        # Message tool
        message_tool = MessageTool(send_callback=self.bus.publish_outbound)
        self.tools.register(message_tool)
        
        # Spawn tool (for subagents)
        spawn_tool = SpawnTool(manager=self.subagents)
        self.tools.register(spawn_tool)
        
        # Cron tool (for scheduling)
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

        # Calendar tool (read-only Google Calendar)
        if self.calendar_client:
            from yak.agent.tools.calendar import CalendarTool
            self.tools.register(CalendarTool(self.calendar_client))

        # Orchestrated workflow tool
        self.tools.register(TextToVideoWorkflowTool(self.text_to_video_workflow))
    
    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        logger.info("Agent loop started")
        
        while self._running:
            try:
                # Wait for next message
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                
                # Process it
                try:
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # Send error response
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}"
                    ))
            except asyncio.TimeoutError:
                continue
    
    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")
    
    async def _process_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a single inbound message.
        
        Args:
            msg: The inbound message to process.
        
        Returns:
            The response message, or None if no response needed.
        """
        # Handle system messages (subagent announces)
        # The chat_id contains the original "channel:chat_id" to route back to
        if msg.channel == "system":
            return await self._process_system_message(msg)
        
        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info(f"Processing message from {msg.channel}:{msg.sender_id}: {preview}")
        
        # Get or create session
        session = self.sessions.get_or_create(msg.session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(msg.channel, msg.chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(msg.channel, msg.chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(msg.channel, msg.chat_id)

        workflow_tool = self.tools.get("text_to_video_workflow")
        if isinstance(workflow_tool, TextToVideoWorkflowTool):
            workflow_tool.set_context(user_id=msg.sender_id, session_id=msg.session_key)
        
        # Build initial messages (use get_history for LLM-formatted messages)
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )
        
        # Agent loop
        iteration = 0
        final_content = None
        last_tool_results: list[str] = []
        sent_work_ack = False
        sent_work_result = False
        
        while iteration < self.max_iterations:
            iteration += 1
            
            # Call LLM
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )

            if (
                response.finish_reason == "error"
                and response.content
                and "Value looks like object, but can't find closing '}' symbol" in response.content
                and last_tool_results
            ):
                final_content = last_tool_results[-1]
                break
            
            # Handle tool calls (native first, then ReAct-style fallback parsing)
            tool_calls = response.tool_calls
            parsed_from_text_fallback = False
            if not tool_calls:
                tool_calls = extract_tool_calls_from_content(response.content)
                if tool_calls:
                    parsed_from_text_fallback = True
                    logger.info("Parsed tool calls from assistant text fallback")

            if tool_calls:
                if (not sent_work_ack) and msg.channel == "discord" and any(tc.name == "text_to_video_workflow" for tc in tool_calls):
                    sent_work_ack = True
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="On it! Generating your video (this can take a couple minutes)...",
                        reply_to=(msg.metadata or {}).get("message_id"),
                        metadata=msg.metadata or {},
                    ))

                assistant_content_for_history = response.content
                reasoning_for_history = response.reasoning_content
                if parsed_from_text_fallback:
                    # Avoid malformed free-form JSON-like text causing downstream Ollama parse errors.
                    assistant_content_for_history = ""
                    reasoning_for_history = None
                messages, tool_results = await apply_tool_calls(
                    messages=messages,
                    context=self.context,
                    tools=self.tools,
                    tool_calls=tool_calls,
                    assistant_content=assistant_content_for_history,
                    reasoning_content=reasoning_for_history,
                    include_tool_call_message=not parsed_from_text_fallback,
                )
                last_tool_results = tool_results
                self._record_tool_results(tool_results)
                self._maybe_failover_model()


                # If the workflow produced a local video and we are responding on Discord,
                # upload it (and include a link) in a single message to avoid double-posting.
                if msg.channel == "discord":
                    for tc, tr in zip(tool_calls, tool_results):
                        if tc.name != "text_to_video_workflow":
                            continue
                        try:
                            obj = json.loads(tr)
                        except Exception:
                            continue
                        if not isinstance(obj, dict):
                            continue

                        remote_url = obj.get("remote_url")
                        video_path = obj.get("video_path")

                        attachments = []
                        if isinstance(video_path, str) and video_path.strip():
                            attachments = [
                                MediaAttachment(
                                    type="video",
                                    path=video_path,
                                    filename=Path(video_path).name,
                                )
                            ]

                        if attachments:
                            content = "Here is your video!"
                        elif isinstance(remote_url, str) and remote_url.strip():
                            content = f"Video link: {remote_url}"
                        else:
                            content = ""

                        if not content and not attachments:
                            continue

                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=content,
                            message_type="video",
                            reply_to=(msg.metadata or {}).get("message_id"),
                            attachments=attachments,
                            metadata=msg.metadata or {},
                        ))
                        sent_work_result = True
                        break

                    if sent_work_result:
                        # We already delivered the result to Discord; stop iterating to avoid extra assistant posts.
                        final_content = ""
                        break
            else:
                # No tool calls, we're done
                self._consecutive_tool_failures = 0
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        # FINAL_CONTENT_WORKFLOW_JSON_FILTER: If the model echoed tool JSON on Discord, show a human output instead.
        if msg.channel == "discord":
            try:
                obj = json.loads(final_content) if isinstance(final_content, str) else None
            except Exception:
                obj = None
            if isinstance(obj, dict) and obj.get("status") == "ok" and obj.get('remote_url'):
                final_content = f"Video link: {obj.get('remote_url')}"
        
        # Log response preview
        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info(f"Response to {msg.channel}:{msg.sender_id}: {preview}")
        
        # Save to session
        session.add_message("user", msg.content)
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        if msg.channel == "discord" and sent_work_result:
            return None

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},  # Pass through for channel-specific needs (e.g. Slack thread_ts)
        )
    
    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        """
        Process a system message (e.g., subagent announce).
        
        The chat_id field contains "original_channel:original_chat_id" to route
        the response back to the correct destination.
        """
        logger.info(f"Processing system message from {msg.sender_id}")
        
        # Parse origin from chat_id (format: "channel:chat_id")
        if ":" in msg.chat_id:
            parts = msg.chat_id.split(":", 1)
            origin_channel = parts[0]
            origin_chat_id = parts[1]
        else:
            # Fallback
            origin_channel = "cli"
            origin_chat_id = msg.chat_id
        
        # Use the origin session for context
        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        
        # Update tool contexts
        message_tool = self.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_context(origin_channel, origin_chat_id)
        
        spawn_tool = self.tools.get("spawn")
        if isinstance(spawn_tool, SpawnTool):
            spawn_tool.set_context(origin_channel, origin_chat_id)
        
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool.set_context(origin_channel, origin_chat_id)
        
        # Build messages with the announce content
        messages = self.context.build_messages(
            history=session.get_history(),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
        )
        
        # Agent loop (limited for announce handling)
        iteration = 0
        final_content = None
        
        while iteration < self.max_iterations:
            iteration += 1
            
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model
            )
            
            tool_calls = response.tool_calls
            if not tool_calls:
                tool_calls = extract_tool_calls_from_content(response.content)
                if tool_calls:
                    logger.info("Parsed tool calls from assistant text fallback")

            if tool_calls:
                parsed_from_text_fallback = False
                if not response.tool_calls and tool_calls:
                    parsed_from_text_fallback = True
                messages, tool_results = await apply_tool_calls(
                    messages=messages,
                    context=self.context,
                    tools=self.tools,
                    tool_calls=tool_calls,
                    assistant_content=response.content,
                    reasoning_content=response.reasoning_content,
                    include_tool_call_message=not parsed_from_text_fallback,
                )
                self._record_tool_results(tool_results)
                self._maybe_failover_model()
            else:
                self._consecutive_tool_failures = 0
                final_content = response.content
                break
        
        if final_content is None:
            final_content = "Background task completed."
        
        # Save to session (mark as system message in history)
        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)
        
        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content
        )
    
    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> str:
        """
        Process a message directly (for CLI or cron usage).
        
        Args:
            content: The message content.
            session_key: Session identifier.
            channel: Source channel (for context).
            chat_id: Source chat ID (for context).
        
        Returns:
            The agent's response.
        """
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content
        )
        
        response = await self._process_message(msg)
        return response.content if response else ""
