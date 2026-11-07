"""Three collaborating uAgents. The Intake agent is chat-facing (Agent Chat Protocol, discoverable in
ASI:One); it delegates to the Test Author and Judge agents with typed messages."""
import os
from datetime import datetime, timezone
from uuid import uuid4

from agents.conversation import Conversation
from agents.protocol import BankReply, BankRequest, JudgeReply, JudgeRequest


def build_agents(conversation: Conversation, seeds: dict[str, str] | None = None, mailbox: bool = True):
    import asyncio

    from uagents import Agent, Context, Protocol
    from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, EndSessionContent, TextContent, chat_protocol_spec

    try:
        asyncio.get_event_loop()
    except RuntimeError:  # Python 3.14 no longer creates a default loop; uAgents expects one
        asyncio.set_event_loop(asyncio.new_event_loop())
    seeds = seeds or {n: os.environ.get(f"SHARLEY_{n.upper()}_SEED", f"sharley-{n}-dev-seed") for n in ("intake", "author", "judge")}
    intake = Agent(name="sharley-intake", seed=seeds["intake"], port=8101, mailbox=mailbox, publish_agent_details=True)
    author = Agent(name="sharley-test-author", seed=seeds["author"], port=8102, mailbox=mailbox, publish_agent_details=True)
    judge = Agent(name="sharley-judge", seed=seeds["judge"], port=8103, mailbox=mailbox, publish_agent_details=True)

    chat = Protocol(spec=chat_protocol_spec)

    @chat.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage):
        await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
        text = "".join(c.text for c in msg.content if isinstance(c, TextContent))
        reply = conversation.handle(sender, text)
        await ctx.send(sender, ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
                                           content=[TextContent(type="text", text=reply.text)]))

    @chat.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    intake.include(chat, publish_manifest=True)

    @author.on_message(BankRequest, replies=BankReply)
    async def on_bank(ctx: Context, sender: str, msg: BankRequest):
        from sharley.schemas import Spec
        try:
            bank = conversation.services.make_bank(Spec.model_validate_json(msg.spec_json))
            await ctx.send(sender, BankReply(ok=True, bank_key=f"{bank.spec_hash}:{bank.seed}",
                                             examples=len(bank.examples), sealed=len(bank.sealed)))
        except Exception as e:
            await ctx.send(sender, BankReply(ok=False, error=f"{type(e).__name__}: retry the request"))

    @judge.on_message(JudgeRequest, replies=JudgeReply)
    async def on_judge(ctx: Context, sender: str, msg: JudgeRequest):
        from agents.repo import clone
        from sharley.judge import load_bank
        from sharley.schemas import ModelRef
        try:
            bank = load_bank(conversation.services.ctx.repo, msg.bank_key)
            v = conversation.services.judge(bank, clone(msg.repo_url, msg.branch),
                                            ModelRef(provider="external", model=msg.implementer_model, family=msg.implementer_family))
            await ctx.send(sender, JudgeReply(ok=True, verdict_json=v.model_dump_json()))
        except Exception as e:
            await ctx.send(sender, JudgeReply(ok=False, error=f"{type(e).__name__}: retry the request"))

    return intake, author, judge
