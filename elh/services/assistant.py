import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import nepali_datetime as nepali

from elh.core.health import HealthService
from elh.core.settings import SettingsService
from elh.integrations.ai.agent import ExternalAIAgent
from elh.repositories import DatabaseGateway
from elh.services.container import ServiceContainer


@dataclass
class AssistantResponse:
    title: str
    content: str
    badge: str = "INFO"
    data_rows: list[dict[str, Any]] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)


class InstituteAssistant:
    """Safe, read-only AI Assistant and Natural Language Query Engine for ELH.

    Guarantees zero mutation of existing data, configs, or schemas.
    """

    def __init__(
        self,
        services: ServiceContainer,
        db: DatabaseGateway,
        external_ai: ExternalAIAgent | None = None,
    ):
        self.services = services
        self.db = db
        if external_ai is not None:
            self.external_ai = external_ai
        else:
            db_gemini_key = ""
            db_provider = "gemini"
            db_model = "gemini-3.6-flash"
            if hasattr(db, "query"):
                try:
                    settings_svc = SettingsService(db)
                    db_gemini_key = settings_svc.get("gemini_api_key", "")
                    db_provider = settings_svc.get("ai_provider", "gemini")
                    db_model = settings_svc.get("ai_model", "gemini-3.6-flash")
                except Exception:
                    pass
            self.external_ai = ExternalAIAgent(
                api_key=db_gemini_key,
                provider=db_provider,
                model=db_model,
            )

    def execute(self, prompt: str) -> AssistantResponse:
        """Parse natural language or slash commands and return structured read-only insights."""
        query = prompt.strip()
        if not query:
            return AssistantResponse(
                title="AI Assistant",
                content="Please enter a command or ask a question. Type /help to see available options.",
                badge="READY",
            )

        lower_query = query.lower()

        # 1. Direct Slash Commands
        if query.startswith("/"):
            return self._handle_slash_command(query)

        # 2. Natural Language Person / Contact / Dues / Details Extraction
        target_person = self._extract_person_target(query)
        if target_person:
            person_result = self._lookup_person(target_person)
            if person_result:
                return person_result
            return AssistantResponse(
                title="Person Lookup",
                content=(
                    f"No student or staff member matching \"{target_person}\" was found in the database.\n\n"
                    "Suggestions:\n"
                    "  • Verify the spelling of the name\n"
                    "  • Try searching by 10-digit mobile number\n"
                    "  • Use /find <query> for partial wildcard matching"
                ),
                badge="NOT FOUND",
                suggested_actions=["/find", "/absent", "/stats"],
            )

        # 3. Natural Language Intent Classification (Aggregate / System)
        if any(w in lower_query for w in ["absent", "not present", "missing today", "who didn't come", "who did not come"]):
            return self._query_absent_today()

        if any(w in lower_query for w in ["present today", "who is present", "attendance today", "checked in", "who attended"]):
            return self._query_present_today()

        if any(w in lower_query for w in ["account", "cash in hand", "cash", "bank", "vault", "wallet balance", "liquidity"]):
            return self._query_account_balances()

        if any(w in lower_query for w in ["due", "unpaid", "outstanding", "fee balance", "fee debt", "arrears"]):
            return self._query_outstanding_dues()

        if any(w in lower_query for w in ["health", "diagnostics", "system status", "backup status", "is device connected"]):
            return self._query_system_health()

        if any(w in lower_query for w in ["stat", "summary", "overview", "total students", "how many students", "metrics"]):
            return self._query_institute_stats()

        if any(w in lower_query for w in ["course", "subjects", "classes offered"]):
            return self._query_courses()

        if any(w in lower_query for w in ["staff", "teacher", "instructors", "faculty"]):
            return self._query_staff()

        if any(w in lower_query for w in ["auto bill", "autobill", "recurring bill", "generate monthly bill", "unbilled student", "monthly invoice", "recurring invoice"]):
            return self._query_auto_billing()

        if any(w in lower_query for w in ["help", "what can you do", "commands"]):
            return self._handle_help()

        # 4. Direct Entity Fallback (if query is a name or phone number)
        direct_match = self._lookup_person(query)
        if direct_match:
            return direct_match

        # 5. External AI Agent Fallback (if configured via OpenAI, Gemini, Ollama, Anthropic)
        if self.external_ai.is_configured():
            system_ctx = self._build_system_context()
            ok, ai_answer = self.external_ai.query(query, system_ctx)
            if ok:
                return AssistantResponse(
                    title="AI Agent Response",
                    content=ai_answer,
                    badge="EXTERNAL AI",
                    suggested_actions=["/stats", "/help"],
                )

        return AssistantResponse(
            title="Assistant Query",
            content=(
                f"I couldn't match a specific automated workflow for: \"{query}\".\n\n"
                "Try asking one of the following:\n"
                "  • \"What is the contact no of [Student Name]?\"\n"
                "  • \"Who is absent today?\"\n"
                "  • \"Show outstanding fee balances\"\n"
                "  • \"Show account and cash balances\"\n"
                "  • \"Search student [Name or Phone]\"\n"
                "  • \"Check system and device health\"\n"
                "  • \"Institute overview statistics\"\n\n"
                "Or ask external AI with: /ai <your question>"
            ),
            badge="HINT",
            suggested_actions=["/absent", "/dues", "/accounts", "/stats", "/health"],
        )

    def _handle_slash_command(self, cmd: str) -> AssistantResponse:
        parts = cmd.split(maxsplit=1)
        action = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if action in {"/help", "/?"}:
            return self._handle_help()
        if action in {"/absent", "/attendance_absent"}:
            return self._query_absent_today()
        if action in {"/present", "/attendance_present"}:
            return self._query_present_today()
        if action in {"/dues", "/outstanding", "/fees"}:
            return self._query_outstanding_dues()
        if action in {"/accounts", "/balances", "/cash"}:
            return self._query_account_balances()
        if action in {"/health", "/diag"}:
            return self._query_system_health()
        if action in {"/stats", "/summary", "/dashboard"}:
            return self._query_institute_stats()
        if action in {"/student", "/find", "/search"}:
            if not arg:
                return AssistantResponse("Student Search", "Usage: /find <name or contact phone>", badge="ERROR")
            return self._search_students(arg)
        if action in {"/courses", "/classes"}:
            return self._query_courses()
        if action in {"/staff", "/teachers"}:
            return self._query_staff()
        if action in {"/poller", "/device"}:
            return self._query_poller_status()
        if action in {"/ai", "/ask", "/gpt", "/gemini", "/claude", "/agent"}:
            if not arg:
                return AssistantResponse("External AI Agent", "Usage: /ai <your question or task>", badge="ERROR")

            # 1. Try external AI if configured
            if self.external_ai.is_configured():
                system_ctx = self._build_system_context()
                ok, ai_answer = self.external_ai.query(arg, system_ctx)
                if ok:
                    return AssistantResponse(
                        title="AI Agent Response",
                        content=ai_answer,
                        badge="EXTERNAL AI",
                        suggested_actions=["/stats", "/help"],
                    )

            # 2. Fallback: Answer institute query from local database records
            local_resp = self.execute(arg)
            if local_resp and local_resp.badge not in {"HINT", "READY"}:
                return local_resp

            # 3. If external AI not configured and local match not found, show helpful setup instructions
            return AssistantResponse(
                title="AI Agent Setup",
                content=(
                    f"External AI provider is not configured for open-ended query: \"{arg}\".\n\n"
                    "To enable external AI agent reasoning, set one of the following in your environment:\n"
                    "  • set OPENAI_API_KEY=sk-...\n"
                    "  • set GEMINI_API_KEY=AIza...\n"
                    "  • set DEEPSEEK_API_KEY=sk-...\n"
                    "  • set GROQ_API_KEY=gsk_...\n"
                    "  • Or run a local Ollama instance (http://localhost:11434)\n\n"
                    "💡 Tip: You can query institute attendance, student contacts, fee balances, and stats directly!"
                ),
                badge="AI SETUP",
                suggested_actions=["/absent", "/dues", "/accounts", "/stats"],
            )
        if action in {"/accounts", "/balances", "/cash"}:
            return self._query_account_balances()
        if action in {"/health", "/diag"}:
            return self._query_system_health()
        if action in {"/stats", "/summary", "/dashboard"}:
            return self._query_institute_stats()
        if action in {"/student", "/find", "/search"}:
            if not arg:
                return AssistantResponse("Student Search", "Usage: /find <name or contact phone>", badge="ERROR")
            return self._search_students(arg)
        if action in {"/courses", "/classes"}:
            return self._query_courses()
        if action in {"/staff", "/teachers"}:
            return self._query_staff()
        if action in {"/poller", "/device"}:
            return self._query_poller_status()
        if action in {"/autobill", "/autoinvoice", "/recurring"}:
            return self._query_auto_billing(arg)

        return AssistantResponse(
            title="Unknown Command",
            content=f"Command '{action}' is not recognized. Type /help to see all commands.",
            badge="ERROR",
            suggested_actions=["/help"],
        )

    def _handle_help(self) -> AssistantResponse:
        content = (
            "🤖 ELH Institute AI Assistant & Query Console\n"
            "--------------------------------------------------\n"
            "Available Natural Language Queries & Slash Commands:\n\n"
            "  /absent            — List students absent today with contacts\n"
            "  /present           — List students punched/present today\n"
            "  /dues              — Summary of highest outstanding fee balances\n"
            "  /accounts          — Real-time bank, cash, and wallet account balances\n"
            "  /autobill [run]    — Automated monthly recurring invoicing status & execution\n"
            "  /find <name/phone> — Search students and their enrollment status\n"
            "  /courses           — List active courses and enrolled counts\n"
            "  /staff             — List active teaching staff\n"
            "  /health            — Hardware, DB, and backup diagnostic report\n"
            "  /poller            — Attendance background poller status\n"
            "  /stats             — Overall institute KPI metrics\n"
            "  /help              — Display this help menu\n\n"
            "💡 You can also type natural questions like:\n"
            "   \"Who didn't come to institute today?\"\n"
            "   \"Show cash in hand and bank balances\"\n"
            "   \"Check unbilled students for this month\"\n"
            "   \"What is our system backup health?\""
        )
        return AssistantResponse(
            title="AI Command Palette",
            content=content,
            badge="HELP",
            suggested_actions=["/stats", "/autobill", "/absent", "/dues", "/accounts", "/health"],
        )

    def _query_auto_billing(self, arg: str = "") -> AssistantResponse:
        service = getattr(self.services, "recurring_billing", None)
        if not service:
            return AssistantResponse(
                title="Automated Recurring Invoicing",
                content="Recurring billing service is not available.",
                badge="ERROR",
            )
        action_arg = arg.strip().lower()
        if action_arg in {"run", "execute", "now", "generate"}:
            res = service.run_auto_billing(actor_username="assistant")
            return AssistantResponse(
                title=f"Auto-Invoicing Result ({res.target_month})",
                content=(
                    f"⚡ Automated Recurring Billing Executed for {res.target_month}:\n\n"
                    f"  • Invoices Created: {res.bills_created}\n"
                    f"  • Skipped / Already Invoiced: {res.bills_skipped}\n"
                    f"  • Total Amount Invoiced: {self.services.billing.currency_symbol} {res.total_invoiced_amount:,.2f}\n"
                    f"  • SMS Notifications Queued: {res.sms_queued_count}\n"
                    f"  • Executed At: {res.executed_at}"
                ),
                badge="COMPLETED",
                suggested_actions=["/dues", "/stats", "/autobill"],
            )

        prev = service.preview()
        cfg = prev["config"]
        unbilled = prev["unbilled_enrollments"]
        content = (
            f"⚡ Automated Monthly Recurring Invoicing Status\n"
            f"--------------------------------------------------\n"
            f"Target Nepali Month: {prev['target_month']}\n"
            f"Daemon Enabled: {'YES (Active)' if cfg['enabled'] else 'NO (Manual only)'}\n"
            f"Due Days Allowance: {cfg['due_days']} days\n"
            f"Auto SMS Notification: {'YES' if cfg['auto_sms'] else 'NO'}\n"
            f"Last Run Month: {cfg['last_run_month'] or 'None'}\n"
            f"Last Run Timestamp: {cfg['last_run_at'] or 'Never'}\n\n"
            f"📋 Unbilled Active Students: {len(unbilled)}\n"
            f"💰 Total Estimated Invoicing: {self.services.billing.currency_symbol} {prev['total_estimated_amount']:,.2f}\n"
        )
        if unbilled:
            content += "\nSample Pending Enrollments:\n"
            for u in unbilled[:6]:
                content += f"  • #{u['enrollment_id']} {u['student_name']} — {u['course_name']} ({self.services.billing.currency_symbol} {u['estimated_amount']:,.2f})\n"
            if len(unbilled) > 6:
                content += f"  ... and {len(unbilled) - 6} more students.\n"
            content += "\n💡 Type '/autobill run' to issue invoices for all unbilled students right now!"
        else:
            content += "\n🎉 All active students are up to date and invoiced for this month!"

        return AssistantResponse(
            title="Auto-Invoicing Status",
            content=content,
            badge="AUTOBILL",
            suggested_actions=["/autobill run", "/dues", "/stats"],
        )

    def _query_absent_today(self) -> AssistantResponse:
        rows = self.services.attendance.students_absent_today()
        if not rows:
            return AssistantResponse(
                title="Today's Attendance",
                content="🎉 No absent students found today (or all enrolled students are marked present/holiday).",
                badge="SUCCESS",
            )
        lines = [f"Found {len(rows)} absent student(s) today:\n"]
        lines.append(f"{'Student Name':<22} | {'Class':<12} | {'Guardian Contact':<15} | {'Course(s)'}")
        lines.append("-" * 75)
        for r in rows:
            name = str(r.get("student_name", ""))[:20]
            cls_name = str(r.get("class_name", "") or "-")[:10]
            contact = str(r.get("contact", "") or "-")[:14]
            courses = str(r.get("courses", "") or "-")[:25]
            lines.append(f"{name:<22} | {cls_name:<12} | {contact:<15} | {courses}")

        return AssistantResponse(
            title="Absent Students Today",
            content="\n".join(lines),
            badge=f"{len(rows)} ABSENT",
            data_rows=rows,
            suggested_actions=["/present", "/stats"],
        )

    def _query_present_today(self) -> AssistantResponse:
        rows = self.services.attendance.students_present_today()
        if not rows:
            return AssistantResponse(
                title="Today's Attendance",
                content="No attendance punches registered yet for today.",
                badge="INFO",
            )
        lines = [f"Found {len(rows)} student(s) present today:\n"]
        lines.append(f"{'Student Name':<22} | {'First Punch':<12} | {'Last Punch':<12} | {'Punches'}")
        lines.append("-" * 65)
        for r in rows:
            name = str(r.get("student_name", ""))[:20]
            first_in = str(r.get("first_punch", "") or "-")[-8:]
            last_out = str(r.get("last_punch", "") or "-")[-8:]
            cnt = str(r.get("punch_count", "1"))
            lines.append(f"{name:<22} | {first_in:<12} | {last_out:<12} | {cnt}")

        return AssistantResponse(
            title="Present Students Today",
            content="\n".join(lines),
            badge=f"{len(rows)} PRESENT",
            data_rows=rows,
            suggested_actions=["/absent", "/stats"],
        )

    def _query_outstanding_dues(self) -> AssistantResponse:
        # Read-only query for top debtors
        rows = self.db.query(
            "SELECT s.id, s.student_name, s.contact, s.class_name, "
            "COALESCE(SUM(st.charge_amount - st.payment_amount - st.discount_amount), 0) AS balance "
            "FROM students s "
            "JOIN student_transactions st ON st.student_id = s.id "
            "WHERE s.status <> 'Archived' "
            "GROUP BY s.id, s.student_name, s.contact, s.class_name "
            "HAVING balance > 0 "
            "ORDER BY balance DESC LIMIT 15"
        )
        total_due = sum(float(r["balance"]) for r in rows)
        if not rows:
            return AssistantResponse(
                title="Outstanding Dues",
                content="🎉 Excellent! There are no outstanding student fee balances recorded.",
                badge="CLEAN",
            )

        lines = [f"Top {len(rows)} student balances (Total Sampled: Rs. {total_due:,.2f}):\n"]
        lines.append(f"{'Student Name':<22} | {'Class':<10} | {'Contact':<14} | {'Due Amount'}")
        lines.append("-" * 65)
        for r in rows:
            name = str(r["student_name"])[:20]
            cls_name = str(r["class_name"] or "-")[:9]
            contact = str(r["contact"] or "-")[:13]
            amt = f"Rs. {float(r['balance']):,.2f}"
            lines.append(f"{name:<22} | {cls_name:<10} | {contact:<14} | {amt}")

        return AssistantResponse(
            title="Outstanding Fee Balances",
            content="\n".join(lines),
            badge=f"{len(rows)} DUES",
            data_rows=[dict(r) for r in rows],
            suggested_actions=["/accounts", "/stats"],
        )

    def _query_account_balances(self) -> AssistantResponse:
        rows = self.db.account_balances()
        active_rows = [r for r in rows if r.get("status") == "Active"]
        total_funds = sum(float(r["balance"] or 0) for r in active_rows)
        lines = [f"Active Accounts ({len(active_rows)}) — Total Liquidity: Rs. {total_funds:,.2f}\n"]
        lines.append(f"{'Account Name':<24} | {'Type':<12} | {'Current Balance'}")
        lines.append("-" * 55)
        for r in active_rows:
            name = str(r["account_name"])[:22]
            atype = str(r["account_type"])[:11]
            bal = f"Rs. {float(r['balance'] or 0):,.2f}"
            lines.append(f"{name:<24} | {atype:<12} | {bal}")

        return AssistantResponse(
            title="Account & Cash Balances",
            content="\n".join(lines),
            badge=f"Rs. {total_funds:,.2f}",
            data_rows=[dict(r) for r in active_rows],
            suggested_actions=["/dues", "/stats"],
        )

    def _query_system_health(self) -> AssistantResponse:
        report = HealthService(self.services.notifications.config).report()
        checked_time = str(report.get("checked_at") or report.get("timestamp") or "Now")
        lines = [
            f"Overall Status: {str(report.get('status', 'OK')).upper()}",
            f"Checked At:     {checked_time}\n",
            f"{'Component':<22} | {'Status':<10} | {'Details'}",
            "-" * 65,
        ]
        for check in report.get("checks", []):
            name = str(check["name"]).replace("_", " ").title()[:20]
            st = str(check["status"]).upper()
            detail = str(check["detail"])[:35]
            lines.append(f"{name:<22} | {st:<10} | {detail}")

        return AssistantResponse(
            title="System & Hardware Diagnostics",
            content="\n".join(lines),
            badge=str(report.get("status", "OK")).upper(),
            data_rows=report.get("checks", []),
            suggested_actions=["/poller", "/stats"],
        )

    def _query_poller_status(self) -> AssistantResponse:
        st = self.services.attendance_poller.status()
        content = (
            f"Attendance Device Background Poller\n"
            f"------------------------------------\n"
            f"  Status:          {'RUNNING' if st['running'] else 'STOPPED'}\n"
            f"  Enabled:         {st['enabled']}\n"
            f"  Poll Interval:   {st['interval_seconds']} seconds\n"
            f"  Last Polled At:  {st['last_polled_at'] or 'Never'}\n"
            f"  Punches Saved:   {st['total_saved_count']} punches (Last cycle: {st['last_saved_count']})\n"
            f"  Cycles Count:    {st['poll_count']}\n"
            f"  Device Healthy:  {'YES' if st['device_healthy'] else 'NO'}\n"
            f"  Last Error:      {st['last_error'] or 'None'}\n"
        )
        return AssistantResponse(
            title="Attendance Poller Status",
            content=content,
            badge="ACTIVE" if st["running"] else "INACTIVE",
        )

    def _query_institute_stats(self) -> AssistantResponse:
        students_count = self.db.query_one("SELECT COUNT(*) AS c FROM students WHERE status<>'Archived'")["c"]
        staff_count = self.db.query_one("SELECT COUNT(*) AS c FROM teachers WHERE status='Active'")["c"]
        enrollments_count = self.db.query_one("SELECT COUNT(*) AS c FROM enrollments WHERE status='Active'")["c"]
        courses_count = self.db.query_one("SELECT COUNT(*) AS c FROM courses WHERE status='Active'")["c"]
        outstanding_row = self.db.query_one(
            "SELECT COALESCE(SUM(charge_amount - payment_amount - discount_amount), 0) AS o "
            "FROM student_transactions"
        )
        outstanding = float(outstanding_row["o"] or 0)

        content = (
            "🏛️ Institute Key Metrics Overview\n"
            "-------------------------------------\n"
            f"  • Total Active Students:   {students_count}\n"
            f"  • Active Staff / Faculty:  {staff_count}\n"
            f"  • Active Enrollments:      {enrollments_count}\n"
            f"  • Active Courses:          {courses_count}\n"
            f"  • Total Outstanding Dues:  Rs. {outstanding:,.2f}\n"
        )
        return AssistantResponse(
            title="Institute KPI Overview",
            content=content,
            badge="METRICS",
            suggested_actions=["/absent", "/dues", "/accounts"],
        )

    def _search_students(self, term: str) -> AssistantResponse:
        pattern = f"%{term.strip()}%"
        rows = self.db.query(
            "SELECT s.id, s.student_name, s.contact, s.class_name, s.status, "
            "COALESCE(sc.school_name, '-') AS school_name "
            "FROM students s "
            "LEFT JOIN schools sc ON sc.id = s.school_id "
            "WHERE (s.student_name LIKE ? OR s.contact LIKE ? OR s.class_name LIKE ?) "
            "AND s.status <> 'Archived' LIMIT 10",
            (pattern, pattern, pattern),
        )
        if not rows:
            return AssistantResponse(
                title="Student Search",
                content=f"No students matching \"{term}\" were found.",
                badge="0 RESULTS",
            )
        lines = [f"Found {len(rows)} matching student(s) for \"{term}\":\n"]
        lines.append(f"{'ID':<5} | {'Student Name':<22} | {'Class':<10} | {'Contact':<14} | {'School'}")
        lines.append("-" * 70)
        for r in rows:
            lines.append(f"{r['id']:<5} | {str(r['student_name'])[:20]:<22} | {str(r['class_name'] or '-'):<10} | {str(r['contact'] or '-'):<14} | {str(r['school_name'])[:18]}")

        return AssistantResponse(
            title=f"Student Search: {term}",
            content="\n".join(lines),
            badge=f"{len(rows)} FOUND",
            data_rows=[dict(r) for r in rows],
        )

    def _query_courses(self) -> AssistantResponse:
        rows = self.db.query(
            "SELECT c.id, c.course_name, c.default_fee, "
            "(SELECT COUNT(*) FROM enrollments e WHERE e.course_id=c.id AND e.status='Active') AS enrolled "
            "FROM courses c WHERE c.status='Active' ORDER BY enrolled DESC"
        )
        lines = [f"Active Courses ({len(rows)}):\n"]
        lines.append(f"{'Course Name':<28} | {'Fee':<12} | {'Enrolled Students'}")
        lines.append("-" * 55)
        for r in rows:
            fee_str = f"Rs. {float(r['default_fee'] or 0):,.2f}"
            lines.append(f"{str(r['course_name'])[:26]:<28} | {fee_str:<12} | {r['enrolled']} active")

        return AssistantResponse(
            title="Course Catalog",
            content="\n".join(lines),
            badge=f"{len(rows)} COURSES",
            data_rows=[dict(r) for r in rows],
        )

    def _query_staff(self) -> AssistantResponse:
        rows = self.db.query(
            "SELECT id, teacher_name, contact, email, staff_type "
            "FROM teachers WHERE status='Active' ORDER BY teacher_name"
        )
        lines = [f"Active Staff & Faculty ({len(rows)}):\n"]
        lines.append(f"{'Name':<24} | {'Role / Type':<16} | {'Contact'}")
        lines.append("-" * 55)
        for r in rows:
            role = str(r["staff_type"] or "Staff") if "staff_type" in r.keys() else "Staff"
            contact = str(r["contact"] or "-") if "contact" in r.keys() else "-"
            lines.append(f"{str(r['teacher_name'])[:22]:<24} | {role[:15]:<16} | {contact}")

        return AssistantResponse(
            title="Staff Directory",
            content="\n".join(lines),
            badge=f"{len(rows)} STAFF",
            data_rows=[dict(r) for r in rows],
        )

    def _extract_person_target(self, query: str) -> str | None:
        """Extract a person name or identifier from common conversational questions."""
        clean = query.strip()
        clean = re.sub(r"[\?\.!,;]+$", "", clean).strip()

        patterns = [
            # How many days is/was/did/does <name> present/attend this month
            r"^(?:how\s+many\s+days\s+(?:is|was|does|did)\s+)(.+?)(?:\s+(?:is|was)?\s*(?:present|attend|attended|come|punched|here))(?:\s+(?:this\s+month|in\s+this\s+month|today|this\s+week))?$",
            # Attendance / present days of <name> (this month)
            r"^(?:attendance|present\s+days?|absent\s+days?)\s+(?:of|for)\s+(.+?)(?:\s+(?:this\s+month|today|this\s+week))?$",
            # What is the contact no of Supriya Adhikari
            r"^(?:what\s+is\s+(?:the\s+)?(?:contact|phone|mobile|cell|email|address|details?|info|dues?|fees?|balance|attendance)(?:\s+(?:no\.?|number))?(?:\s+(?:of|for))?\s+)(.+)$",
            # Contact no of Supriya
            r"^(?:contact|phone|mobile|cell|email|address|details?|info)(?:\s+(?:no\.?|number))?(?:\s+(?:of|for))\s+(.+)$",
            # Tell me the contact of / Tell me about Supriya
            r"^(?:tell\s+me\s+(?:about|the\s+details\s+of|the\s+contact\s+of|the\s+phone\s+of|the\s+number\s+of|the\s+attendance\s+of)\s+)(.+)$",
            # Who is Supriya Adhikari (exclude aggregate questions like absent/present)
            r"^(?:who\s+is\s+)(?!(?:absent|present|here|missing|not\s+here))(.+)$",
            # Where does Supriya live
            r"^(?:where\s+does\s+)(.+?)(?:\s+live)?$",
            # How much does Supriya owe
            r"^(?:how\s+much\s+(?:does|is)\s+)(.+?)(?:\s+(?:owe|due|dues|fee|have\s+to\s+pay))?$",
            # Is/Did Supriya present/come today
            r"^(?:is|did)\s+(?!(?:device|poller|system|backup))(.+?)\s+(?:present|absent|here|in\s+class|come|attend|punch)(?:\s+today)?$",
            # Dues / Fee of Supriya
            r"^(?:dues?|fees?|balance)\s+(?:of|for)\s+(.+)$",
            # Search / find student Supriya
            r"^(?:search|find|lookup|show|get)\s+(?:student|teacher|staff|person|profile|contact\s+of)\s+(.+)$",
        ]

        lower = clean.lower()
        for pat in patterns:
            m = re.match(pat, lower, flags=re.IGNORECASE)
            if m:
                target = m.group(1).strip()
                target = re.sub(r"\b(today|now|please|sir|madam)\b", "", target, flags=re.IGNORECASE).strip()
                if len(target) >= 2:
                    return target

        return None

    def _lookup_person(self, target: str) -> AssistantResponse | None:
        """Deep entity lookup for student or staff with full profile, contact, fees, and attendance."""
        clean_target = re.sub(r"[^\w\s]", " ", target).strip()
        if not clean_target or len(clean_target) < 2:
            return None

        pattern = f"%{clean_target}%"
        students = self.db.query(
            "SELECT s.id, s.student_name, s.class_name, s.contact, s.parent_name, "
            "s.guardian_relationship, s.gender, s.date_of_birth, s.address, s.status, s.joining_date, "
            "COALESCE(sc.school_name, '-') AS school_name "
            "FROM students s "
            "LEFT JOIN schools sc ON sc.id = s.school_id "
            "WHERE s.student_name LIKE ? OR s.contact LIKE ? OR s.parent_name LIKE ? "
            "ORDER BY s.id DESC LIMIT 5",
            (pattern, pattern, pattern),
        )

        # Fallback to first token matching if multi-word name not found directly
        if not students and " " in clean_target:
            tokens = [t for t in clean_target.split() if len(t) >= 3]
            if tokens:
                token_pattern = f"%{tokens[0]}%"
                students = self.db.query(
                    "SELECT s.id, s.student_name, s.class_name, s.contact, s.parent_name, "
                    "s.guardian_relationship, s.gender, s.date_of_birth, s.address, s.status, s.joining_date, "
                    "COALESCE(sc.school_name, '-') AS school_name "
                    "FROM students s "
                    "LEFT JOIN schools sc ON sc.id = s.school_id "
                    "WHERE s.student_name LIKE ? OR s.contact LIKE ? "
                    "ORDER BY s.id DESC LIMIT 5",
                    (token_pattern, token_pattern),
                )

        teachers = self.db.query(
            "SELECT t.id, t.teacher_name, t.contact, t.email, t.staff_type, t.subject, t.status "
            "FROM teachers t "
            "WHERE t.teacher_name LIKE ? OR t.contact LIKE ? OR t.email LIKE ? "
            "ORDER BY t.id DESC LIMIT 5",
            (pattern, pattern, pattern),
        )

        if not students and not teachers:
            return None

        today_ad = datetime.now().date()
        today_start = f"{today_ad} 00:00:00"
        today_end = f"{today_ad} 23:59:59"

        try:
            today_bs = nepali.date.today()
            month_start_bs = nepali.date(today_bs.year, today_bs.month, 1)
            month_start_ad = month_start_bs.to_datetime_date()
            month_start_str = f"{month_start_ad} 00:00:00"
            month_name = month_start_bs.strftime("%B %Y")
        except Exception:
            month_start_str = f"{today_ad.year}-{today_ad.month:02d}-01 00:00:00"
            month_name = "This Month"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = []

        # Student Cards
        for s in students:
            s_id = s["id"]
            s_name = s["student_name"]
            contact = s["contact"] or "Not specified"
            parent = s["parent_name"] or "Not specified"
            guardian_rel = s["guardian_relationship"] or "Guardian"
            class_name = s["class_name"] or "Unassigned"
            school = s["school_name"] or "-"
            address = s["address"] or "Not recorded"
            status = s["status"] or "Active"

            enrollments = self.db.query(
                "SELECT c.course_name FROM enrollments e "
                "JOIN courses c ON c.id=e.course_id "
                "WHERE e.student_id=? AND e.status='Active'",
                (s_id,),
            )
            course_names = ", ".join(r["course_name"] for r in enrollments) if enrollments else "No active courses"

            dues_row = self.db.query_one(
                "SELECT COALESCE(SUM(charge_amount - payment_amount - discount_amount), 0) AS due "
                "FROM student_transactions WHERE student_id=?",
                (s_id,),
            )
            due_amount = float(dues_row["due"] or 0) if dues_row else 0.0

            # Today's Punch
            today_punch = self.db.query_one(
                "SELECT COUNT(*) AS count, MIN(occurred_at) AS first_punch, MAX(occurred_at) AS last_punch "
                "FROM attendance_logs "
                "WHERE person_type='student' AND person_id=? AND occurred_at BETWEEN ? AND ?",
                (s_id, today_start, today_end),
            )
            if today_punch and today_punch["count"]:
                first_punch_val = str(today_punch["first_punch"])
                first_time = first_punch_val[11:16] if len(first_punch_val) >= 16 else first_punch_val
                att_str = f"Present today ({today_punch['count']} punch(es), First: {first_time})"
            else:
                att_str = "No punch recorded today (Absent / Off)"

            # Monthly Attendance Days
            month_rows = self.db.query(
                "SELECT substr(occurred_at, 1, 10) AS punch_date, COUNT(*) AS punches "
                "FROM attendance_logs "
                "WHERE person_type='student' AND person_id=? AND occurred_at BETWEEN ? AND ? "
                "GROUP BY substr(occurred_at, 1, 10)",
                (s_id, month_start_str, now_str),
            )
            days_present = len(month_rows)
            total_month_punches = sum(r["punches"] for r in month_rows)

            lines.append(f"🎓 Student: {s_name} (ID #{s_id}) — Status: {status}")
            lines.append("-" * 55)
            lines.append(f"  📞 Contact No:         {contact}")
            lines.append(f"  👨‍👩‍👧 Guardian / Parent:  {parent} ({guardian_rel})")
            lines.append(f"  🏫 Class / School:     {class_name} | {school}")
            lines.append(f"  📍 Address:            {address}")
            lines.append(f"  📚 Active Courses:     {course_names}")
            lines.append(f"  💰 Outstanding Fee:    Rs. {due_amount:,.2f}" + (" (Cleared)" if due_amount <= 0 else " (Unpaid Dues)"))
            lines.append(f"  🕒 Today's Status:     {att_str}")
            lines.append(f"  📊 Monthly Attendance: {days_present} day(s) present in {month_name} ({total_month_punches} total punches)")
            lines.append("")

        # Staff Cards
        for t in teachers:
            t_id = t["id"]
            t_name = t["teacher_name"]
            contact = t["contact"] or "Not specified"
            email = t["email"] or "Not specified"
            staff_type = (t["staff_type"] or "Staff") if "staff_type" in t.keys() else "Staff"
            subject = (t["subject"] or "-") if "subject" in t.keys() else "-"
            status = t["status"] or "Active"

            today_punch_t = self.db.query_one(
                "SELECT COUNT(*) AS count, MIN(occurred_at) AS first_punch "
                "FROM attendance_logs "
                "WHERE person_type='teacher' AND person_id=? AND occurred_at BETWEEN ? AND ?",
                (t_id, today_start, today_end),
            )
            if today_punch_t and today_punch_t["count"]:
                att_str_t = f"Present today ({today_punch_t['count']} punch(es))"
            else:
                att_str_t = "No punch recorded today"

            month_rows_t = self.db.query(
                "SELECT substr(occurred_at, 1, 10) AS punch_date, COUNT(*) AS punches "
                "FROM attendance_logs "
                "WHERE person_type='teacher' AND person_id=? AND occurred_at BETWEEN ? AND ? "
                "GROUP BY substr(occurred_at, 1, 10)",
                (t_id, month_start_str, now_str),
            )
            days_present_t = len(month_rows_t)

            lines.append(f"👨‍🏫 Staff: {t_name} (ID #{t_id}) — Status: {status}")
            lines.append("-" * 55)
            lines.append(f"  📞 Contact No:         {contact}")
            lines.append(f"  ✉️ Email:              {email}")
            lines.append(f"  🏷️ Role / Type:        {staff_type}")
            lines.append(f"  📖 Subject / Dept:     {subject}")
            lines.append(f"  🕒 Today's Status:     {att_str_t}")
            lines.append(f"  📊 Monthly Attendance: {days_present_t} day(s) present in {month_name}")
            lines.append("")

        first_contact = students[0]["contact"] if students else (teachers[0]["contact"] if teachers else "")
        primary_name = students[0]["student_name"] if students else (teachers[0]["teacher_name"] if teachers else clean_target)

        return AssistantResponse(
            title=f"Contact & Profile: {primary_name}",
            content="\n".join(lines).strip(),
            badge=f"📞 {first_contact}" if first_contact else "MATCH FOUND",
            data_rows=[dict(r) for r in students] + [dict(r) for r in teachers],
            suggested_actions=["/dues", "/absent", "/stats"],
        )

    def _build_system_context(self) -> str:
        """Construct safe, lightweight system context to assist external AI agents."""
        try:
            today_bs = nepali.date.today().strftime("%Y/%m/%d")
        except Exception:
            today_bs = "Today"

        try:
            courses = self.db.query("SELECT course_name FROM courses WHERE status='Active' LIMIT 15")
            course_list = ", ".join(c["course_name"] for c in courses)
        except Exception:
            course_list = "Standard courses"

        return (
            f"Context: Today's date is {today_bs} BS ({datetime.now().strftime('%Y-%m-%d')} AD). "
            f"Institute: Expert Learning Hub (ELH), Nepal. Active courses: {course_list}."
        )
