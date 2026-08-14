"""
NLP Engine — builds SQL directly from natural language.
Fixed version — resolves all extraction bugs.
"""

import re
import spacy
from dataclasses import dataclass, field
from typing import Optional
from difflib import get_close_matches

nlp = spacy.load("en_core_web_sm")

# ── Aggregate keywords — whole word match only ────────────────────────────────
# Each entry: (func, [keywords], whole_word_required)
AGGREGATE_KEYWORDS = [
    ("COUNT", ["how many", "count", "number of", "total number"]),
    ("SUM",   ["sum of", "sum", "combined", "overall"]),
    ("AVG",   ["average", "avg", "mean", "typical"]),
    ("MAX",   ["highest", "maximum", "most expensive", "peak", "largest", "biggest"]),
    ("MIN",   ["lowest", "minimum", "cheapest", "least expensive", "smallest"]),
]

# These words should NOT trigger aggregates when they appear as part of other words
AGG_FALSE_POSITIVES = {
    "many": ["germany", "company", "romany", "botany", "harmony"],
    "total": [],   # "total" itself is fine but "total X" where X is a filter = no SUM
    "sum":   [],
}

ORDER_KEYWORDS = {
    "DESC": ["highest", "most", "top", "best", "largest", "biggest",
             "descending", "desc", "maximum", "leading", "greatest", "expensive"],
    "ASC":  ["lowest", "least", "bottom", "worst", "smallest",
             "ascending", "asc", "minimum", "cheapest"],
}

COMPARISON_PATTERNS = [
    (r"(?:more than|greater than|over|above|exceeding)\s+(\d+(?:\.\d+)?)",  ">"),
    (r"(?:less than|under|below|beneath)\s+(\d+(?:\.\d+)?)",                "<"),
    (r"(?:at least|no less than|minimum of)\s+(\d+(?:\.\d+)?)",             ">="),
    (r"(?:at most|no more than|up to|maximum of)\s+(\d+(?:\.\d+)?)",        "<="),
    (r"between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)",                 "BETWEEN"),
    (r"(?:equals?|is exactly|exactly)\s+(\d+(?:\.\d+)?)",                   "="),
]

TEMPORAL_PATTERNS = {
    "today":       "date('now')",
    "yesterday":   "date('now', '-1 day')",
    "this week":   "strftime('%W-%Y', date('now'))",
    "last week":   "strftime('%W-%Y', date('now', '-7 days'))",
    "this month":  "strftime('%m-%Y', date('now'))",
    "last month":  "strftime('%m-%Y', date('now', '-1 month'))",
    "this year":   "strftime('%Y', date('now'))",
    "last year":   "strftime('%Y', date('now', '-1 year'))",
}

YEAR_PATTERN   = re.compile(r"\b(19|20)\d{2}\b")
LIMIT_PATTERN  = re.compile(
    r"\b(?:top|first|bottom)\s+(\d+)\b"
    r"|\b(\d+)\s+(?:records?|rows?|results?|entries|items?)\b",
    re.IGNORECASE
)

# Group by triggers — ordered longest first to avoid partial matches
GROUP_TRIGGERS = [
    "breakdown by ", "grouped by ", "group by ",
    "distribution by ", "split by ", "by each ",
    "for each ", "per ",
]


@dataclass
class JoinClause:
    table:    str
    on_left:  str
    on_right: str


@dataclass
class WhereClause:
    col:      str
    operator: str
    value:    str


@dataclass
class QueryPlan:
    original:        str
    tables:          list = field(default_factory=list)
    joins:           list = field(default_factory=list)
    aggregate:       Optional[str] = None
    aggregate_col:   Optional[str] = None
    where_clauses:   list = field(default_factory=list)
    group_by:        Optional[str] = None
    order_by:        Optional[str] = None
    order_dir:       str = "DESC"
    limit:           Optional[int] = None
    temporal_filter: Optional[str] = None
    needs_llm:       bool = False


class NLPEngine:
    def __init__(self, schema: dict):
        self.schema     = schema
        self.all_tables = list(schema["tables"].keys())
        self.col_map    = self._build_col_map()
        self.fk_map     = self._build_fk_map()

    # ── Schema helpers ────────────────────────────────────────────────────────

    def _build_col_map(self) -> dict:
        """col_name_lower → [Table, Table, ...]"""
        m = {}
        for table, info in self.schema["tables"].items():
            for col in info["columns"]:
                m.setdefault(col["name"].lower(), []).append(table)
        return m

    def _build_fk_map(self) -> list:
        fks = []
        for table, info in self.schema["tables"].items():
            for fk in info.get("foreign_keys", []):
                fks.append({
                    "table":     table,
                    "col":       fk["from"][0],
                    "ref_table": fk["to_table"],
                    "ref_col":   fk["to_cols"][0],
                })
        return fks

    def fuzzy_table(self, word: str) -> Optional[str]:
        w = word.lower()
        for t in self.all_tables:
            if t.lower() == w:
                return t
        variants = [w, w+"s", w+"es", w.rstrip("s"), w.rstrip("es")]
        for v in variants:
            for t in self.all_tables:
                if t.lower() == v:
                    return t
        lower = [t.lower() for t in self.all_tables]
        close = get_close_matches(w, lower, n=1, cutoff=0.7)
        if close:
            return self.all_tables[lower.index(close[0])]
        return None

    def fuzzy_col(self, word: str, table: str) -> Optional[str]:
        """Match word to a column in the given table."""
        cols  = [c["name"] for c in self.schema["tables"][table]["columns"]]
        lower = [c.lower() for c in cols]
        w     = word.lower()
        # exact
        if w in lower:
            return cols[lower.index(w)]
        # partial — col contains word or word contains col
        for i, c in enumerate(lower):
            if w in c or c in w:
                return cols[i]
        # fuzzy
        close = get_close_matches(w, lower, n=1, cutoff=0.6)
        if close:
            return cols[lower.index(close[0])]
        return None

    def find_numeric_col(self, table: str) -> Optional[str]:
        cols = self.schema["tables"][table]["columns"]
        pks  = self.schema["tables"][table].get("primary_keys", [])
        preferred = ["total","amount","price","salary","revenue",
                     "cost","quantity","qty","value","score","rating","unitprice"]
        for pref in preferred:
            for col in cols:
                if pref in col["name"].lower() and col["name"] not in pks:
                    return col["name"]
        for col in cols:
            if any(t in str(col["type"]).upper()
                   for t in ["REAL","FLOAT","DECIMAL","NUMERIC","NUMBER"]):
                if col["name"] not in pks:
                    return col["name"]
        return None

    def find_date_col(self, table: str) -> Optional[str]:
        cols = self.schema["tables"][table]["columns"]
        for hint in ["date","time","created","updated","hired","born","joined"]:
            for col in cols:
                if hint in col["name"].lower():
                    return col["name"]
        for col in cols:
            if any(t in str(col["type"]).upper()
                   for t in ["DATE","TIME","DATETIME","TIMESTAMP"]):
                return col["name"]
        return None

    def find_join_path(self, t1: str, t2: str) -> Optional[JoinClause]:
        for fk in self.fk_map:
            if fk["table"].lower() == t1.lower() and fk["ref_table"].lower() == t2.lower():
                return JoinClause(t2, f"{t1}.{fk['col']}", f"{t2}.{fk['ref_col']}")
            if fk["table"].lower() == t2.lower() and fk["ref_table"].lower() == t1.lower():
                return JoinClause(t2, f"{t1}.{fk['ref_col']}", f"{t2}.{fk['col']}")
        return None

    # ── Extraction methods ────────────────────────────────────────────────────

    # Semantic synonyms — maps domain words to table names
    SEMANTIC_TABLE_MAP = {
        "revenue":     ["Invoice"],
        "sales":       ["Invoice"],
        "sale":        ["Invoice"],
        "purchase":    ["Invoice"],
        "purchases":   ["Invoice"],
        "order":       ["Invoice"],
        "orders":      ["Invoice"],
        "transaction": ["Invoice"],
        "transactions":["Invoice"],
        "earning":     ["Invoice"],
        "earnings":    ["Invoice"],
        "song":        ["Track"],
        "songs":       ["Track"],
        "music":       ["Track"],
        "band":        ["Artist"],
        "bands":       ["Artist"],
        "record":      ["Album"],
        "records":     ["Album"],
        "user":        ["Customer"],
        "users":       ["Customer"],
        "client":      ["Customer"],
        "clients":     ["Customer"],
        "buyer":       ["Customer"],
        "buyers":      ["Customer"],
        "country":     ["Invoice", "Customer"],
        "countries":   ["Invoice", "Customer"],
        "price":       ["Track"],
        "prices":      ["Track"],
        "total":   ["Invoice"],
        "revenue": ["Invoice"],
        "sales":   ["Invoice"],
    }

    def extract_tables(self, text: str) -> list:
        """Extract table names — check every word, lemma, and semantic synonyms."""
        found = []
        doc   = nlp(text)

        # spaCy lemmas
        for token in doc:
            if len(token.text) > 2:
                m = self.fuzzy_table(token.lemma_)
                if m and m not in found:
                    found.append(m)

        # Raw words
        for word in re.findall(r'[a-zA-Z]+', text):
            if len(word) > 2:
                m = self.fuzzy_table(word)
                if m and m not in found:
                    found.append(m)

        # Semantic synonyms — map domain words to tables
        text_lower = text.lower()
        for synonym, tables in self.SEMANTIC_TABLE_MAP.items():
            if re.search(r'\b' + re.escape(synonym) + r'\b', text_lower):
                for t in tables:
                    if t in self.all_tables and t not in found:
                        found.append(t)

        return found

    def extract_aggregate(self, text: str, has_numeric_filter: bool) -> Optional[str]:
        """
        Extract aggregate function.
        Key fixes:
        - Whole-word matching only
        - 'total' alone does NOT mean SUM if there's already a numeric filter
        - 'many' only matches as standalone word not inside 'Germany' etc
        """
        text_lower = text.lower()

        for func, keywords in AGGREGATE_KEYWORDS:
            for kw in keywords:
                # Use word boundary matching
                pattern = r'\b' + re.escape(kw) + r'\b'
                if re.search(pattern, text_lower):
                    # Special case: SUM triggered by "total" but query has comparison filter
                    # e.g. "invoices with total more than 10" → filter query not SUM
                    if func == "SUM" and kw == "total" and has_numeric_filter:
                        continue
                    # Special case: "total X" where X is a table name = COUNT/SELECT not SUM
                    # e.g. "total invoices per customer" = count invoices grouped by customer
                    if func == "SUM" and kw in ("total", "sum"):
                        # Check if next word is a table name
                        match = re.search(r'\b' + re.escape(kw) + r'\s+(\w+)', text_lower)
                        if match:
                            next_word = match.group(1)
                            if self.fuzzy_table(next_word):
                                return "COUNT"
                    return func
        return None

    def extract_limit(self, text: str) -> Optional[int]:
        m = LIMIT_PATTERN.search(text)
        if m:
            return int(m.group(1) or m.group(2))
        return None

    def extract_order(self, text: str) -> tuple:
        """Returns (col_hint, direction). Handles multi-word columns like 'unit price'."""
        text_lower = text.lower()
        direction  = "DESC"
        for dir_key, keywords in ORDER_KEYWORDS.items():
            if any(re.search(r'\b' + re.escape(kw) + r'\b', text_lower)
                   for kw in keywords):
                direction = dir_key
                break

        # "by <col>" or "by <word> <word>" — capture up to 2 words after "by"
        match = re.search(r'\bby\s+(\w+(?:\s+\w+)?)', text_lower)
        col_hint = match.group(1).strip() if match else None

        # Exclude group-by triggers from order-by
        if col_hint:
            for trigger in ["each", "customer", "genre", "category", "month",
                            "year", "country", "region", "department"]:
                if col_hint.startswith(trigger):
                    col_hint = None
                    break

        return col_hint, direction

    def extract_filters(self, text: str, tables: list) -> list:
        """Extract WHERE conditions — both numeric and string."""
        filters    = []
        text_lower = text.lower()

        # Numeric comparisons
        for pattern, operator in COMPARISON_PATTERNS:
            for m in re.finditer(pattern, text_lower, re.IGNORECASE):
                # Find preceding noun as column hint
                chunk = text_lower[max(0, m.start()-60):m.start()]
                words = chunk.split()
                skip  = {"than","to","at","most","least","more","less","over",
                         "under","above","below","between","from","is","with",
                         "where","and","or","invoices","customers","tracks","the","a"}
                col_hint = None
                for w in reversed(words):
                    w = re.sub(r'[^a-z]', '', w)
                    if w and w not in skip and len(w) > 1:
                        col_hint = w
                        break

                if operator == "BETWEEN":
                    filters.append(WhereClause(
                        col=self._resolve_col(col_hint, tables),
                        operator="BETWEEN",
                        value=f"{m.group(1)} AND {m.group(2)}"
                    ))
                else:
                    filters.append(WhereClause(
                        col=self._resolve_col(col_hint, tables),
                        operator=operator,
                        value=m.group(1)
                    ))

        # String equality filters
        # Strip order/group/sort by clauses first
        text_no_orderby = re.sub(
            r'\b(?:order(?:ed)?|sort(?:ed)?|group(?:ed)?)\s+by\s+\w+',
            '', text, flags=re.IGNORECASE
        )

        # Words that look like values but are NOT filter values
        skip_vals = {
            "the","a","an","of","and","or","with","where","by","for",
            "count","sum","avg","max","min","total","average","order",
            "ordered","group","grouped","asc","desc","ascending",
            "descending","all","each","now","also","too","only","just",
            "show","get","list","top","bottom","first","last","best",
            "worst","filter","filtered","display","fetch","give","find",
            "how","many","number","what","which","who","when","select",
            "from","join","on","where","having","limit","offset",
        }

        string_patterns = [
    # "from Germany", "in USA" — capital letter
    (r'\b(?:from|in|at|located in|based in)\s+([A-Z][a-zA-Z]{2,})', False),
    # "filter by Germany" or "filter by germany" — case insensitive  ← fix this line
    (r'\bfilter(?:ed)?\s+by\s+([A-Za-z][a-zA-Z]{2,})', True),
    # "country is Germany"
    (r'\b(?:country|city|status|category|type|department|genre)'
     r'\s+(?:is\s+)?["\']?([A-Za-z][a-zA-Z]{2,})["\']?', False),
]

        for pat, case_insensitive in string_patterns:
            flags = re.IGNORECASE if case_insensitive else 0
            for m in re.finditer(pat, text_no_orderby, flags):
                val = m.group(1).strip()
                # Capitalize first letter for proper nouns like country names
                val = val[0].upper() + val[1:] if val else val
                if val and val.lower() not in skip_vals and len(val) > 2:
                    col = self._find_string_col(val, tables, text)
                    if col:
                        filters.append(WhereClause(
                            col=col,
                            operator="=",
                            value=f"'{val}'"
                        ))

        return filters

    def _find_string_col(self, value: str, tables: list, text: str) -> Optional[str]:
        """Find the right column for a string filter value."""
        text_lower = text.lower()

        # Priority 1: explicit column hints in text
        col_hints = {
            "country": ["country", "billingcountry", "shipcountry"],
            "city":    ["city", "billingcity"],
            "name":    ["name", "firstname", "lastname"],
            "status":  ["status"],
            "genre":   ["name"],
            "type":    ["type", "mediatype"],
        }
        for hint, col_names in col_hints.items():
            if hint in text_lower:
                for table in tables:
                    cols = [c["name"].lower() for c in self.schema["tables"][table]["columns"]]
                    for col_name in col_names:
                        if col_name in cols:
                            idx = cols.index(col_name)
                            actual = self.schema["tables"][table]["columns"][idx]["name"]
                            return f"{table}.{actual}"

        # Priority 2: value looks like a country/city (capital letter word)
        # Search all tables for country/city columns
        geo_col_names = ["country", "billingcountry", "city", "billingcity",
                        "state", "region", "location"]
        for table in tables:
            cols = [c["name"].lower() for c in self.schema["tables"][table]["columns"]]
            for geo in geo_col_names:
                if geo in cols:
                    idx = cols.index(geo)
                    actual = self.schema["tables"][table]["columns"][idx]["name"]
                    return f"{table}.{actual}"

        # Priority 3: any TEXT column that isn't a PK
        for table in tables:
            pks = self.schema["tables"][table].get("primary_keys", [])
            for col in self.schema["tables"][table]["columns"]:
                if "TEXT" in str(col["type"]).upper() and col["name"] not in pks:
                    return f"{table}.{col['name']}"

        return None

    def _resolve_col(self, hint: str, tables: list) -> Optional[str]:
        """Resolve a column hint to table.column."""
        if not hint:
            return None
        # Try multi-word hint (e.g. "unit price" → "unitprice" or "UnitPrice")
        compact = hint.replace(" ", "")
        for table in tables:
            col = self.fuzzy_col(hint, table)
            if col:
                return f"{table}.{col}"
            col = self.fuzzy_col(compact, table)
            if col:
                return f"{table}.{col}"
        return None

    def extract_group_by(self, text: str, tables: list) -> Optional[str]:
        """
        Extract GROUP BY column.
        Handles: 'per customer', 'by genre', 'for each country', 'grouped by status'
        Also handles COUNT/SUM queries with 'by X' where X is not an order column.
        """
        text_lower = text.lower()

        # Check explicit group triggers first
        for trigger in GROUP_TRIGGERS:
            idx = text_lower.find(trigger)
            if idx != -1:
                after = text[idx + len(trigger):].strip().split()
                if after:
                    word = re.sub(r'[^a-zA-Z]', '', after[0])
                    if word and len(word) > 1:
                        col = self._resolve_col(word, tables)
                        if col:
                            return col
                        # Maybe it's a table name — use its PK
                        t = self.fuzzy_table(word)
                        if t and t in tables:
                            pk = self.schema["tables"][t].get("primary_keys", [])
                            if pk:
                                return f"{t}.{pk[0]}"
                        return word

        # "count X by Y", "total X by Y", "average X by Y" — Y is GROUP BY
        match = re.search(
            r'\b(?:count|total|sum|average|avg)\s+\w+\s+by\s+(\w+)',
            text_lower
        )
        if match:
            word = match.group(1)
            # Could be a table name → use its PK
            t = self.fuzzy_table(word)
            if t and t in tables:
                pk = self.schema["tables"][t].get("primary_keys", [])
                if pk:
                    return f"{t}.{pk[0]}"
            col = self._resolve_col(word, tables)
            if col:
                return col

        # "aggregate X by Y" where Y is followed by filter words or end
        # Handles: "average invoice total by customer from USA"
        #           "total sales by country"  "count orders by status"
        match = re.search(
            r'\bby\s+(\w+)(?:\s+(?:from|in|where|with|having|order|group|limit)|\s*$)',
            text_lower
        )
        if match:
            word = match.group(1)
            skip = {"count","sum","avg","average","total","asc","desc",
                    "each","all","the","a","an","order","group"}
            if word not in skip:
                t = self.fuzzy_table(word)
                if t and t in tables:
                    pk = self.schema["tables"][t].get("primary_keys", [])
                    if pk:
                        return f"{t}.{pk[0]}"
                col = self._resolve_col(word, tables)
                if col:
                    return col

        return None

    def extract_temporal(self, text: str, tables: list) -> list:
        """Extract temporal WHERE clauses."""
        text_lower = text.lower()
        filters    = []

        for phrase, expr in TEMPORAL_PATTERNS.items():
            if phrase in text_lower:
                for table in tables:
                    date_col = self.find_date_col(table)
                    if date_col:
                        filters.append(WhereClause(
                            col=f"{table}.{date_col}",
                            operator="=",
                            value=expr
                        ))
                        break

        year = YEAR_PATTERN.search(text)
        if year:
            for table in tables:
                date_col = self.find_date_col(table)
                if date_col:
                    filters.append(WhereClause(
                        col=f"strftime('%Y', {table}.{date_col})",
                        operator="=",
                        value=f"'{year.group(0)}'"
                    ))
                    break

        return filters

    # ── Main pipeline ─────────────────────────────────────────────────────────

    def build_plan(self, text: str) -> QueryPlan:
        plan = QueryPlan(original=text)

        # 1 — Tables
        plan.tables = self.extract_tables(text)
        if not plan.tables:
            plan.needs_llm = True
            return plan

        primary = plan.tables[0]

        # 2 — Numeric filters first (needed for aggregate detection)
        has_numeric = bool(re.search(
            r'\b(?:more than|less than|over|above|under|below|between|at least|at most)\s+\d',
            text.lower()
        ))

        # 3 — Aggregate (aware of numeric filters)
        plan.aggregate = self.extract_aggregate(text, has_numeric)

        # 4 — Limit
        plan.limit = self.extract_limit(text)

        # 5 — Group by
        plan.group_by = self.extract_group_by(text, plan.tables)

        # 6 — Order + direction
        order_hint, plan.order_dir = self.extract_order(text)
        # Special case: "by total/revenue/amount" — look in FK-linked tables
        if order_hint and order_hint.lower() in ("total", "revenue", "amount", "price", "sales"):
            for fk in self.fk_map:
                if fk["table"].lower() in [t.lower() for t in plan.tables]:
                    ref_table = fk["ref_table"]
                    col = self.fuzzy_col(order_hint, ref_table)
                    if col:
                        if ref_table not in plan.tables:
                            plan.tables.append(ref_table)
                        plan.order_by = f"{ref_table}.{col}"
                        print(f"[nlp] Resolved '{order_hint}' → {plan.order_by} via FK")
                        break
        # 7 — Resolve aggregate column
        if plan.aggregate in ("SUM","AVG","MAX","MIN"):
            if order_hint:
                col = self._resolve_col(order_hint, plan.tables)
                plan.aggregate_col = col.split(".")[-1] if col else None
            if not plan.aggregate_col:
                plan.aggregate_col = self.find_numeric_col(primary)

        # 8 — Resolve order-by column
        if order_hint and not plan.group_by:
            # "top 5 customers by total" — 'total' is in Invoice not Customer
            # Try all tables including join targets
            all_candidate_tables = plan.tables[:]
            for fk in self.fk_map:
                if fk["table"] in plan.tables:
                    if fk["ref_table"] not in all_candidate_tables:
                        all_candidate_tables.append(fk["ref_table"])
                if fk["ref_table"] in plan.tables:
                    if fk["table"] not in all_candidate_tables:
                        all_candidate_tables.append(fk["table"])

            col = self._resolve_col(order_hint, all_candidate_tables)
            if col:
                # If column is in a different table, add that table and join
                col_table = col.split(".")[0]
                if col_table not in plan.tables:
                    plan.tables.append(col_table)
                plan.order_by = col
            elif plan.aggregate_col:
                plan.order_by = f"{primary}.{plan.aggregate_col}"
        elif plan.limit and not plan.aggregate and not plan.order_by:
            # TOP N with no explicit order → use numeric col
            num_col = self.find_numeric_col(primary)
            if num_col:
                plan.order_by = f"{primary}.{num_col}"

        # 9 — Build JOINs for all tables
        if len(plan.tables) > 1:
            primary = plan.tables[0]
            joined  = {primary.lower()}
            for other in plan.tables[1:]:
                if other.lower() in joined:
                    continue
                join = self.find_join_path(primary, other)
                if join:
                    plan.joins.append(join)
                    joined.add(other.lower())
                else:
                    # Try reverse
                    join = self.find_join_path(other, primary)
                    if join:
                        plan.joins.append(JoinClause(
                            other,
                            join.on_right,
                            join.on_left
                        ))
                        joined.add(other.lower())
                    else:
                        # Try via intermediate table
                        for mid in self.all_tables:
                            if mid.lower() in joined:
                                continue
                            j1 = self.find_join_path(primary, mid)
                            j2 = self.find_join_path(mid, other)
                            if j1 and j2:
                                plan.tables.append(mid)
                                plan.joins.append(j1)
                                plan.joins.append(j2)
                                joined.add(mid.lower())
                                joined.add(other.lower())
                                break

        # 10 — WHERE filters
        all_tables_for_filter = list({
            t for t in plan.tables + [j.table for j in plan.joins]
        })
        plan.where_clauses = self.extract_filters(text, all_tables_for_filter)
        plan.where_clauses += self.extract_temporal(text, all_tables_for_filter)

        return plan

    def plan_to_sql(self, plan: QueryPlan) -> str:
        if not plan.tables:
            raise ValueError("No tables identified")

        primary = plan.tables[0]
        parts   = []

        # ── Rebuild JOINs if tables were added by memory but joins are missing ──
        if len(plan.tables) > 1 and len(plan.joins) < len(plan.tables) - 1:
            plan.joins = []
            joined     = {primary.lower()}
            for other in plan.tables[1:]:
                if other.lower() in joined:
                    continue
                join = self.find_join_path(primary, other)
                if join:
                    plan.joins.append(join)
                    joined.add(other.lower())
                else:
                    join = self.find_join_path(other, primary)
                    if join:
                        plan.joins.append(JoinClause(other, join.on_right, join.on_left))
                        joined.add(other.lower())
                    else:
                        for mid in list(joined):
                            mid_actual = next(
                                (t for t in plan.tables if t.lower() == mid), mid
                            )
                            j1 = self.find_join_path(mid_actual, other)
                            if j1:
                                plan.joins.append(j1)
                                joined.add(other.lower())
                                break

        # ── Auto-add JOINs needed by filter columns ──────────────────────────
        joined_tables = {primary} | {j.table for j in plan.joins}
        for w in plan.where_clauses:
            if not w.col or "." not in str(w.col):
                continue
            filter_table = w.col.split(".")[0]
            if filter_table not in joined_tables:
                join = self.find_join_path(primary, filter_table)
                if not join:
                    join = self.find_join_path(filter_table, primary)
                    if join:
                        join = JoinClause(filter_table, join.on_right, join.on_left)
                if not join:
                    # Try via existing joined tables
                    for jt in list(joined_tables):
                        join = self.find_join_path(jt, filter_table)
                        if join:
                            break
                        join = self.find_join_path(filter_table, jt)
                        if join:
                            join = JoinClause(filter_table, join.on_right, join.on_left)
                            break
                if join and join.table not in joined_tables:
                    plan.joins.append(join)
                    joined_tables.add(join.table)
                    print(f"[sql] Auto-added JOIN {filter_table} for filter")

        # ── SELECT clause ─────────────────────────────────────────────────────
        if plan.aggregate == "COUNT":
            if plan.group_by:
                display_col = self._get_display_col(plan.group_by)
                if display_col and display_col != plan.group_by:
                    parts.append(f"SELECT {display_col}, COUNT(*) AS total_count")
                else:
                    parts.append(f"SELECT {plan.group_by}, COUNT(*) AS total_count")
            else:
                parts.append("SELECT COUNT(*) AS total_count")

        elif plan.aggregate in ("SUM", "AVG", "MAX", "MIN"):
            col   = plan.aggregate_col or "*"
            if col != "*" and "." not in col:
                col = f"{primary}.{col}"
            alias = plan.aggregate.lower() + "_value"
            if plan.group_by:
                parts.append(f"SELECT {plan.group_by}, {plan.aggregate}({col}) AS {alias}")
            else:
                parts.append(f"SELECT {plan.aggregate}({col}) AS {alias}")

        else:
            if plan.joins:
                select_parts = [f"{primary}.*"]
                for join in plan.joins:
                    jt      = join.table
                    cols    = self.schema["tables"][jt]["columns"]
                    pks     = self.schema["tables"][jt].get("primary_keys", [])
                    fk_cols = [fk["col"] for fk in self.fk_map if fk["table"] == jt]
                    extra   = [
                        f"{jt}.{c['name']}"
                        for c in cols
                        if c["name"] not in pks and c["name"] not in fk_cols
                    ]
                    select_parts.extend(extra[:6])
                parts.append(f"SELECT {', '.join(select_parts)}")
            else:
                parts.append(f"SELECT {primary}.*")

        # ── FROM ──────────────────────────────────────────────────────────────
        parts.append(f"FROM {primary}")

        # ── JOINs ─────────────────────────────────────────────────────────────
        for join in plan.joins:
            parts.append(f"JOIN {join.table} ON {join.on_left} = {join.on_right}")

        # ── WHERE ─────────────────────────────────────────────────────────────
        valid = [w for w in plan.where_clauses if w.col]
        if valid:
            conditions = []
            for w in valid:
                if w.operator == "BETWEEN":
                    conditions.append(f"{w.col} BETWEEN {w.value}")
                else:
                    conditions.append(f"{w.col} {w.operator} {w.value}")
            parts.append(f"WHERE {' AND '.join(conditions)}")

        # ── GROUP BY ──────────────────────────────────────────────────────────
        if plan.group_by:
            parts.append(f"GROUP BY {plan.group_by}")

        # ── ORDER BY ──────────────────────────────────────────────────────────
        if plan.aggregate == "COUNT":
            pass  # COUNT queries don't need ORDER BY unless grouped
        elif plan.order_by:
            if plan.order_by.lower() in ("count", "total_count", "count(*)"):
                parts.append(f"ORDER BY total_count {plan.order_dir}")
            else:
                parts.append(f"ORDER BY {plan.order_by} {plan.order_dir}")
        elif plan.aggregate == "COUNT" and plan.group_by:
            parts.append(f"ORDER BY total_count {plan.order_dir}")
        elif plan.aggregate in ("SUM", "AVG") and plan.group_by:
            parts.append(f"ORDER BY {plan.aggregate.lower()}_value {plan.order_dir}")

        # ── LIMIT (skip for COUNT without GROUP BY) ───────────────────────────
        if plan.limit and plan.aggregate != "COUNT":
            parts.append(f"LIMIT {plan.limit}")

        return "\n".join(parts)

    def _get_display_col(self, group_col: str) -> Optional[str]:
        """
        If group_col is an ID column (e.g. Genre.GenreId),
        return the Name column instead (Genre.Name) for readable output.
        """
        if not group_col or "." not in group_col:
            return group_col
        table, col = group_col.split(".", 1)
        if table not in self.schema["tables"]:
            return group_col
        cols = [c["name"] for c in self.schema["tables"][table]["columns"]]
        # If it's a PK/ID col, prefer Name
        if col in self.schema["tables"][table].get("primary_keys", []):
            for c in cols:
                if c.lower() in ("name", "title", "label", "description"):
                    return f"{table}.{c}"
        return group_col

    def process(self, text: str) -> dict:
        plan = self.build_plan(text)

        if plan.needs_llm:
            return {"sql": None, "plan": plan, "needs_llm": True,
                    "reason": "Could not identify tables"}

        try:
            sql = self.plan_to_sql(plan)
            return {"sql": sql, "plan": plan, "needs_llm": False}
        except Exception as e:
            return {"sql": None, "plan": plan, "needs_llm": True, "reason": str(e)}