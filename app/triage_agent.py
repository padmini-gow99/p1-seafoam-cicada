from dotenv import load_dotenv
load_dotenv()

import os
import json
from typing import Optional, Annotated, List
from typing_extensions import TypedDict

from fastapi import FastAPI
from pydantic import BaseModel

from langgraph.graph import StateGraph, END, add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage
from langchain_openai import ChatOpenAI

from app.database import get_order_by_id


# -----------------------------
# LLM CONFIG
# -----------------------------
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    api_key=os.getenv("OPENAI_API_KEY"),
)


# -----------------------------
# ISSUE NORMALIZATION
# -----------------------------
_ALLOWED_ISSUES = {
    "update_status",
    "general_question",
    "damaged_item",
    "late_delivery",
    "wrong_item",
    "missing_refund",
}

def normalize_issue_type(raw: Optional[str]) -> str:
    if not raw:
        return "general_question"

    value = raw.strip().lower()
    aliases = {
        "order_update": "update_status",
        "status update": "update_status",
        "shipping": "general_question",
        "general": "general_question",
    }
    normalized = aliases.get(value, value)
    return normalized if normalized in _ALLOWED_ISSUES else "general_question"


# -----------------------------
# STATE
# -----------------------------
class TriageState(TypedDict, total=False):
    messages: Annotated[List[AnyMessage], add_messages]
    ticket_text: str
    query: Optional[str]
    order_id: Optional[str]
    issue_type: Optional[str]
    evidence: Optional[str]
    recommendation: Optional[str]
    reply: Optional[str]
    call_tool: Optional[bool]
    tool_result: Optional[dict]


# -----------------------------
# TOOL (WITH DOCSTRING ✅)
# -----------------------------
def fetch_order_tool(order_id: str) -> dict:
    """
    Fetch order details using an order ID.
    Returns order metadata such as product name, status, and price.
    """
    order = get_order_by_id(order_id)

    if not order:
        return {"found": False, "error": f"Order {order_id} not found"}

    return {
        "found": True,
        "id": order.id,
        "product_name": order.product_name,
        "status": order.status,
        "price": order.price,
        "customer_name": order.customer_name,
    }


# -----------------------------
# NODES
# -----------------------------
def ingest(state: TriageState) -> dict:
    messages = state.get("messages", [])
    messages.append(HumanMessage(content=state["ticket_text"]))

    if state.get("query"):
        messages.append(HumanMessage(content=f"Customer query: {state['query']}"))

    if state.get("order_id"):
        messages.append(HumanMessage(content=f"Provided order_id: {state['order_id']}"))

    return {"messages": messages}


def classify_issue(state: TriageState) -> dict:
    system_prompt = """
Return ONLY JSON:
{
  "issue_type": "...",
  "order_id": "... or null",
  "evidence": "...",
  "call_tool": true or false
}
"""
    response = llm.invoke(
        [HumanMessage(content=system_prompt)] + state["messages"]
    )

    try:
        parsed = json.loads(response.content)
    except Exception:
        parsed = {}

    return {
        "messages": state["messages"] + [AIMessage(content=response.content)],
        "issue_type": normalize_issue_type(parsed.get("issue_type")),
        "order_id": parsed.get("order_id") or state.get("order_id"),
        "evidence": parsed.get("evidence"),
        "call_tool": parsed.get("call_tool", False),
    }


def draft_reply(state: TriageState) -> dict:
    system_prompt = """
Return ONLY JSON:
{
  "reply": "...",
  "recommendation": "...",
  "issue_type": "...",
  "order_id": "...",
  "evidence": "..."
}
"""
    messages = list(state["messages"])

    if state.get("tool_result"):
        messages.append(
            HumanMessage(content=f"Order context: {state['tool_result']}")
        )

    response = llm.invoke([HumanMessage(content=system_prompt)] + messages)

    try:
        parsed = json.loads(response.content)
    except Exception:
        parsed = {}

    return {
        "reply": parsed.get("reply", "Thank you, we are reviewing your request."),
        "recommendation": parsed.get("recommendation", "review_manually"),
        "issue_type": normalize_issue_type(
            parsed.get("issue_type", state.get("issue_type"))
        ),
        "order_id": parsed.get("order_id", state.get("order_id")),
        "evidence": parsed.get("evidence", state.get("evidence")),
        "messages": messages,
    }


# -----------------------------
# GRAPH ROUTING
# -----------------------------
def route_after_classification(state: TriageState) -> str:
    if state.get("call_tool") and state.get("order_id"):
        return "fetch_order"
    return "draft_reply"


def build_graph():
    graph = StateGraph(TriageState)

    graph.add_node("ingest", ingest)
    graph.add_node("classify_issue", classify_issue)

    graph.add_node(
        "fetch_order",
        ToolNode([fetch_order_tool])  # ✅ ToolNode
    )

    graph.add_node("draft_reply", draft_reply)

    graph.set_entry_point("ingest")

    graph.add_edge("ingest", "classify_issue")

    graph.add_conditional_edges(
        "classify_issue",
        route_after_classification,
        {
            "fetch_order": "fetch_order",
            "draft_reply": "draft_reply",
        },
    )

    graph.add_edge("fetch_order", "draft_reply")
    graph.add_edge("draft_reply", END)

    return graph.compile()


TRIAGE_GRAPH = build_graph()


# -----------------------------
# FASTAPI
# -----------------------------
app = FastAPI()


class TriageInput(BaseModel):
    ticket_text: str
    order_id: Optional[str] = None
    query: Optional[str] = None


@app.post("/triage/invoke")
def triage(input: TriageInput):
    initial_state: TriageState = {
        "ticket_text": input.ticket_text,
        "order_id": input.order_id,
        "query": input.query,
        "messages": [],
    }

    result = TRIAGE_GRAPH.invoke(initial_state)

    return {
        "reply": result.get("reply"),
        "issue_type": result.get("issue_type"),
        "order_id": result.get("order_id"),
        "evidence": result.get("evidence"),
        "recommendation": result.get("recommendation"),
    }
