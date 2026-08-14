"""
True conversational memory for multi-turn NL-to-SQL.
Resolves pronouns, merges filters, inherits context across turns.
"""

from dataclasses import dataclass, field
from typing import Optional
from copy import deepcopy


# Words that signal a follow-up query (not a fresh question)
FOLLOWUP_SIGNALS = [
    "them", "those", "these", "they", "their", "same",
    "also", "too", "additionally", "furthermore", "as well",
    "now", "but", "except", "instead", "rather", "more",
    "sort", "order", "filter", "show", "add", "include",
]

# Words that signal the user wants to REPLACE something
REPLACE_SIGNALS = {
    "instead":  ["order_by", "aggregate"],
    "rather":   ["order_by", "aggregate"],
    "only":     ["filters"],
    "just":     ["filters"],
    "forget":   ["filters", "joins"],
    "reset":    ["filters", "joins", "limit"],
    "start over": ["all"],
    "new query":  ["all"],
}

# Pronoun → refers to previous subject
PRONOUNS = ["them", "those", "these", "they", "their",
            "it", "its", "that", "which"]


@dataclass
class ConversationTurn:
    """One turn in the conversation."""
    turn_number:  int
    raw_query:    str
    tables:       list
    joins:        list
    filters:      list
    aggregate:    Optional[str]
    aggregate_col:Optional[str]
    group_by:     Optional[str]
    order_by:     Optional[str]
    order_dir:    str
    limit:        Optional[int]
    sql:          str


class ConversationMemory:
    """
    Stores full conversation history and resolves each new query
    against previous context — enabling true multi-turn dialogue.
    """

    def __init__(self):
        self.turns:   list[ConversationTurn] = []
        self.turn_num: int = 0

    def store(self, plan, sql: str):
        """Store a completed query plan as a conversation turn."""
        self.turn_num += 1
        turn = ConversationTurn(
            turn_number   = self.turn_num,
            raw_query     = plan.original,
            tables        = plan.tables[:],
            joins         = deepcopy(plan.joins),
            filters       = deepcopy(plan.where_clauses),
            aggregate     = plan.aggregate,
            aggregate_col = plan.aggregate_col,
            group_by      = plan.group_by,
            order_by      = plan.order_by,
            order_dir     = plan.order_dir,
            limit         = plan.limit,
            sql           = sql,
        )
        self.turns.append(turn)
        print(f"[memory] Stored turn {self.turn_num}: {plan.original[:50]}")

    def resolve(self, plan, raw_query: str):
        if not self.turns:
            return plan

        last  = self.turns[-1]
        text  = raw_query.lower().strip()

        is_followup   = self._detect_followup(text, plan)
        replace_flags = self._detect_replace(text)

        if not is_followup:
            return plan

        print(f"[memory] Follow-up detected: '{raw_query}'")

        # ── Step 1: Inherit tables ────────────────────────────────────────────
        if not plan.tables:
            plan.tables = last.tables[:]
            plan.joins  = deepcopy(last.joins)
            print(f"[memory] Inherited tables: {plan.tables}")

        # ── Step 2: Handle "show their X too" — expand tables ────────────────
        if self._has_pronoun(text) and plan.tables:
            new_tables = [t for t in plan.tables if t not in last.tables]
            if new_tables:
                # Start from last tables, add new ones
                combined = last.tables[:]
                for t in new_tables:
                    if t not in combined:
                        combined.append(t)
                plan.tables = combined
                # Rebuild joins from scratch for expanded table set
                plan.joins = []
                print(f"[memory] Expanded tables to: {plan.tables}")

        # ── Step 3: Inherit filters ───────────────────────────────────────────
        current_set = set(t.lower() for t in plan.tables)
        last_set    = set(t.lower() for t in last.tables)
        overlap     = bool(current_set & last_set)
        has_pronoun = self._has_pronoun(text)

        if "all" in replace_flags or "filters" in replace_flags:
            pass
        elif not plan.where_clauses and last.filters:
            for f in last.filters:
                if not f.col:
                    continue
                col_table = f.col.split(".")[0] if "." in f.col else None
                # Inherit if: same tables, pronoun reference, or col table joinable
                if col_table in plan.tables or has_pronoun or overlap:
                    plan.where_clauses.append(deepcopy(f))
                    # Also add the filter's table if needed for JOIN
                    if col_table and col_table not in plan.tables:
                        plan.tables.append(col_table)
                        print(f"[memory] Added {col_table} to tables for filter")
            if plan.where_clauses:
                print(f"[memory] Inherited {len(plan.where_clauses)} filter(s)")
        # ── Step 4: Order by ──────────────────────────────────────────────────
        if "order_by" in replace_flags or "instead" in text or "sort" in text:
            pass  # new order — keep what NLP found
        elif not plan.order_by and last.order_by:
            order_table = last.order_by.split(".")[0] if "." in str(last.order_by) else None
            if order_table and order_table in plan.tables:
                plan.order_by  = last.order_by
                plan.order_dir = last.order_dir
                print(f"[memory] Inherited order_by: {last.order_by}")
            else:
                print(f"[memory] Skipped order_by (table not in query)")

        # ── Step 5: Limit ─────────────────────────────────────────────────────
        if plan.limit is None and last.limit:
            if overlap:
                plan.limit = last.limit
                print(f"[memory] Inherited limit: {last.limit}")
            else:
                print(f"[memory] Skipped limit inheritance (different tables)")

        # ── Step 6: Inherit aggregate for "how many/count" ───────────────────
        if any(w in text for w in ["how many", "count", "number of", "total count"]):
            plan.aggregate     = "COUNT"
            plan.aggregate_col = None
            plan.order_by      = None
            plan.limit         = None   # ← add this line
            print(f"[memory] Set aggregate: COUNT")

        # ── Step 7: Group by ─────────────────────────────────────────────────
        if not plan.group_by and last.group_by:
            if any(w in text for w in ["group", "per ", "each"]):
                plan.group_by = last.group_by

        return plan

    def _detect_followup(self, text: str, plan) -> bool:
        # Has explicit follow-up signal words
        if any(sig in text for sig in FOLLOWUP_SIGNALS):
            return True
        # Has pronouns referring to previous subject
        if self._has_pronoun(text):
            return True
        # No tables found but last turn had tables
        if not plan.tables and self.turns:
            return True
        # Very short query AND no clear table found (likely a refinement)
        if len(text.split()) <= 3 and not plan.tables and self.turns:
            return True
        # If query has its own clear tables — NOT a followup
        if plan.tables:
            return False
        return False

    def _detect_replace(self, text: str) -> set:
        """Detect what the user wants to replace vs inherit."""
        flags = set()
        for signal, targets in REPLACE_SIGNALS.items():
            if signal in text:
                flags.update(targets)
        return flags

    def _has_pronoun(self, text: str) -> bool:
        """Check if text contains pronouns referring to previous context."""
        words = text.split()
        return any(w in PRONOUNS for w in words)

    def clear(self):
        self.turns    = []
        self.turn_num = 0
        print("[memory] Conversation cleared.")
    def _get_fks(self, table: str) -> list:
        """Get all tables FK-linked to given table."""
        # We don't have schema here so return empty — 
        # schema awareness added in next fix
        return []
    @property
    def has_context(self) -> bool:
        return len(self.turns) > 0

    @property
    def last_sql(self) -> Optional[str]:
        return self.turns[-1].sql if self.turns else None

    @property
    def history_summary(self) -> list:
        """Returns a summary of conversation history for the frontend."""
        return [
            {
                "turn":  t.turn_number,
                "query": t.raw_query,
                "tables": t.tables,
                "sql_preview": t.sql[:80] + "..." if len(t.sql) > 80 else t.sql,
            }
            for t in self.turns
        ]