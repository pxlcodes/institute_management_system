"""Website Content Management System (CMS) Service."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


DEFAULT_CMS_SECTIONS: dict[str, Any] = {
    "hero": {
        "badge": "Leading Coaching & Tech Mentorship in Morang",
        "title": "Empowering Future Leaders & Tech Innovators",
        "subtitle": "Expert Learning Hub bridges traditional secondary education with modern robotics, IoT engineering, and global career pathways. From SEE toppers to international scholars, your journey starts here.",
        "cta_primary_text": "Explore Courses",
        "cta_primary_link": "#courses",
        "cta_secondary_text": "IoT Mentorship",
        "cta_secondary_link": "#iot",
        "announcement_text": "Admissions open for SEE 2083 Batch & Korean / Japanese Language Classes!",
        "announcement_active": True,
    },
    "general": {
        "name": "Expert Learning Hub",
        "tagline": "Redefining Education Through Excellence & Innovation",
        "address": "Expert Tower, Shikar Chowk, Pathari Shanishchare-1, Morang, Nepal",
        "phone": "+977 9800924090",
        "alt_phone": "+977 9842121118",
        "email": "info@expertlearninghub.edu.np",
        "working_hours": "Sun - Fri: 6:00 AM - 7:00 PM",
        "facebook_url": "https://facebook.com/expertlearninghub",
        "youtube_url": "https://youtube.com/@expertlearninghub",
        "instagram_url": "https://instagram.com/expertlearninghub",
        "tiktok_url": "https://tiktok.com/@expertlearninghub",
        "map_embed_url": "",
    },
    "stats": {
        "students_count": "500+",
        "students_label": "Students Mentored",
        "teachers_count": "14+",
        "teachers_label": "Expert Educators",
        "success_rate": "98%",
        "success_label": "Academic Success Rate",
        "projects_count": "25+",
        "projects_label": "IoT & Tech Capstones",
    },
    "courses": [
        {
            "id": 1,
            "title": "Grade 10 SEE Master Class",
            "category": "secondary",
            "category_label": "Secondary (8-10)",
            "duration": "Full Academic Year",
            "fee_note": "Includes model exams & study sets",
            "badge": "Flagship",
            "description": "Intensive revision and concept mastery across Compulsory Math, Science, OPT Math, and English with weekly model exams and individual reviews.",
            "topics": [
                "Compulsory Mathematics & Science Mastery",
                "Optional Mathematics & Advanced Numerical Practice",
                "Weekly Strict SEE Model Board Examinations",
                "Doubt-Clearing Labs & Personalized Weak-Area Mentoring"
            ],
            "status": "Published"
        },
        {
            "id": 2,
            "title": "Grade 9 Academic Excellence",
            "category": "secondary",
            "category_label": "Secondary (8-10)",
            "duration": "Full Academic Year",
            "fee_note": "Monthly installment available",
            "badge": "Popular",
            "description": "Building strong foundational roots in Science and Mathematics to prepare students smoothly for the upcoming Grade 10 board year.",
            "topics": [
                "Comprehensive Core Curriculum Coverage",
                "Conceptual Science Experiments & Practical Insight",
                "Problem-Solving Speed & Mental Math Techniques",
                "Regular Progress Analytics & Parent Counseling"
            ],
            "status": "Published"
        },
        {
            "id": 3,
            "title": "Grade 8 Basic Level (BLE) Coaching",
            "category": "secondary",
            "category_label": "Secondary (8-10)",
            "duration": "Full Academic Year",
            "fee_note": "Term-wise fee structure",
            "badge": "Core Foundation",
            "description": "Targeted preparation for the District/Municipality BLE examination, instilling disciplined study habits and solid conceptual clarity.",
            "topics": [
                "BLE Board Syllabus Comprehensive Tracking",
                "Grammar, Reading Comprehension & Nepali Writing",
                "Math Problem Drill Series",
                "Monthly Diagnostic Assessments"
            ],
            "status": "Published"
        },
        {
            "id": 4,
            "title": "+2 Science Core & Entrance Prep",
            "category": "plus2",
            "category_label": "+2 Science & Commerce",
            "duration": "Academic Year",
            "fee_note": "Includes entrance guidance",
            "badge": "Advanced",
            "description": "Deep-dive coaching in Physics, Chemistry, and Mathematics/Biology tailored to NEB board exams and competitive medical/engineering entrance standards.",
            "topics": [
                "Physics Numerical Workshops & Mechanics Mastery",
                "Organic & Inorganic Chemistry Reaction Mechanisms",
                "Calculus, Vectors & Applied Mathematics",
                "Medical & Engineering Entrance Question Analysis"
            ],
            "status": "Published"
        },
        {
            "id": 5,
            "title": "+2 Commerce, Accounts & Economics",
            "category": "plus2",
            "category_label": "+2 Science & Commerce",
            "duration": "Academic Year",
            "fee_note": "Practical ledger software training",
            "badge": "Career Track",
            "description": "Master financial accounting, micro/macro economics, and business mathematics taught by experienced chartered accountants and college lecturers.",
            "topics": [
                "Double Entry Bookkeeping & Corporate Financial Statements",
                "Economic Analysis & National Income Models",
                "Business Mathematics & Statistical Interpretation",
                "Case Studies on Nepalese Banking and Commerce"
            ],
            "status": "Published"
        },
        {
            "id": 6,
            "title": "Bridge Course (After SEE)",
            "category": "plus2",
            "category_label": "+2 Science & Commerce",
            "duration": "3 Months (Intensive)",
            "fee_note": "Special scholarship test available",
            "badge": "Bridge Course",
            "description": "High-yield transition program bridging the leap between Class 10 and Class 11 Science/Management, plus entrance exam prep for top colleges.",
            "topics": [
                "College Entrance MCQ Speed Drills",
                "Early Jumpstart on 11th Grade Science & Management",
                "Personality Development & Career Guidance",
                "Mock Entrance Tests for Premier Higher Secondary Colleges"
            ],
            "status": "Published"
        },
        {
            "id": 7,
            "title": "Tech & IoT Engineering Mentorship",
            "category": "tech",
            "category_label": "Tech & IoT",
            "duration": "3 - 6 Months",
            "fee_note": "Hardware kit included in lab",
            "badge": "Tech Lab Flagship",
            "description": "Hands-on engineering lab where students construct practical IoT devices, program ESP32 microcontrollers, connect cloud sensors, and build real prototypes.",
            "topics": [
                "ESP32 / Arduino Microcontroller Programming in C++",
                "Sensor Interfacing: Temperature, Ultrasonic, PIR, Gas & Relays",
                "Cloud Telemetry, MQTT Protocols & Live Web Dashboards",
                "Capstone Project: Smart Home Automation & Agriculture Prototype"
            ],
            "status": "Published"
        },
        {
            "id": 8,
            "title": "Korean Language (EPS-TOPIK Track)",
            "category": "language",
            "category_label": "Global Languages",
            "duration": "4 - 6 Months",
            "fee_note": "Exam test sets included",
            "badge": "HRD Korea EPS",
            "description": "Comprehensive Korean language coaching designed specifically for passing the HRD Korea EPS-TOPIK examination for employment in South Korea.",
            "topics": [
                "Hangul Alphabet, Pronunciation & Vocabulary Drills",
                "EPS-TOPIK Grammar Rules & Sentence Structures",
                "Audio Listening Simulation Labs with Real Test Audio",
                "Weekly Computer-Based Test (CBT) Practice"
            ],
            "status": "Published"
        },
        {
            "id": 9,
            "title": "Japanese Language (NAT-TEST / JLPT)",
            "category": "language",
            "category_label": "Global Languages",
            "duration": "4 - 6 Months",
            "fee_note": "Study visa guidance included",
            "badge": "JLPT N5-N3",
            "description": "Native-guided Japanese training covering Hiragana, Katakana, Kanji, and conversational fluency for NAT-TEST, JLPT N5/N4, and study in Japan.",
            "topics": [
                "Hiragana, Katakana & Essential 150+ Kanji Characters",
                "Minna no Nihongo Standard Curriculum",
                "Conversational Japanese & Cultural Etiquette",
                "NAT-TEST & JLPT Examination Strategies"
            ],
            "status": "Published"
        },
        {
            "id": 10,
            "title": "English Fluency & IELTS Coaching",
            "category": "language",
            "category_label": "Global Languages",
            "duration": "2 - 3 Months",
            "fee_note": "Free diagnostic placement test",
            "badge": "Top Rated",
            "description": "Sharpen your spoken English confidence, academic writing, and international test readiness for IELTS Academic/General Training.",
            "topics": [
                "IELTS Band 7+ Strategies (Listening, Reading, Writing, Speaking)",
                "Daily Public Speaking & Group Debate Sessions",
                "Academic Essay Writing & Vocabulary Enrichment",
                "Full-Length Weekly Mock Exams with Band Score Feedback"
            ],
            "status": "Published"
        }
    ],
    "iot_showcase": {
        "badge": "Future-Proof Technology",
        "title": "Hardware, Embedded Firmware & Cloud Telemetry",
        "subtitle": "We don't just teach theory. Our dedicated robotics and IoT lab gives students hands-on experience building smart devices with ESP32, Raspberry Pi, sensors, and cloud dashboards.",
        "cta_text": "Enroll in IoT Program",
        "cta_link": "#inquiry",
        "highlights": [
            {
                "title": "ESP32 & Microcontroller Architecture",
                "desc": "GPIO programming, I2C/SPI sensor interfaces, and embedded C++ / MicroPython fundamentals."
            },
            {
                "title": "Sensor Integration & Robotics",
                "desc": "Ultrasonic, temperature, gas, motion sensors, and motor-driven automation kits."
            },
            {
                "title": "Cloud Dashboards & MQTT",
                "desc": "Connecting real-world sensors to web dashboards and live mobile telemetry."
            },
            {
                "title": "Real-World Engineering Projects",
                "desc": "Smart agriculture, automatic lighting, environmental monitors, and home automation."
            }
        ]
    },
    "languages": [
        {
            "id": 1,
            "name": "Korean Language (EPS-TOPIK)",
            "badge": "HRD Korea EPS",
            "code": "KR",
            "target_exam": "EPS-TOPIK Manufacturing & Agriculture",
            "duration": "4 - 6 Months",
            "description": "Structured grammar, high-frequency vocabulary, and continuous CBT model testing to secure top scores in the EPS employment system.",
            "features": ["Daily CBT practice", "Native audio listening labs", "Interview guidance"]
        },
        {
            "id": 2,
            "name": "Japanese Language (NAT / JLPT)",
            "badge": "NAT / JLPT N5-N3",
            "code": "JP",
            "target_exam": "NAT-TEST, JLPT & J-CERT",
            "duration": "4 - 6 Months",
            "description": "Comprehensive course following Minna no Nihongo, covering Kanji mastery, listening comprehension, and interview preparation for Japan visas.",
            "features": ["Kanji writing workshops", "Visa interview simulation", "Cultural immersion"]
        },
        {
            "id": 3,
            "name": "English Fluency & IELTS",
            "badge": "IELTS Band 7+",
            "code": "EN",
            "target_exam": "IELTS Academic & General",
            "duration": "2 - 3 Months",
            "description": "Speaking confidence, accent refinement, and rigorous four-skill IELTS coaching for global academic and migration success.",
            "features": ["One-on-one speaking drills", "Essay correction clinic", "Mock test score analysis"]
        }
    ],
    "pillars": [
        {
            "id": 1,
            "title": "Concept Mastery",
            "subtitle": "No Rote Learning",
            "desc": "We build deep first-principles intuition in Science, Mathematics, and Languages rather than superficial memorization.",
            "icon": "brain"
        },
        {
            "id": 2,
            "title": "Continuous Evaluation",
            "subtitle": "Weekly Model Exams",
            "desc": "Regular mock examinations simulate board conditions, pinpointing weak areas for rapid, targeted intervention.",
            "icon": "chart"
        },
        {
            "id": 3,
            "title": "Hands-on Mentorship",
            "subtitle": "Robotics & IoT Lab",
            "desc": "Students gain practical engineering and programming skills by designing real electronics prototypes in our lab.",
            "icon": "cpu"
        },
        {
            "id": 4,
            "title": "Global Pathways",
            "subtitle": "Language & Career Hub",
            "desc": "Specialized Korean, Japanese, and English training open international employment and higher education gateways.",
            "icon": "globe"
        }
    ],
    "events": [
        {
            "id": 1,
            "title": "International Education & Career Pathways Webinar",
            "category": "Webinar",
            "date": "Every Alternate Saturday",
            "venue": "ELH Main Auditorium & Zoom",
            "desc": "Comprehensive briefing on post-SEE bridge courses, higher secondary subject selection, and global study options.",
            "status": "Upcoming"
        },
        {
            "id": 2,
            "title": "Global Tech, Robotics & AI Innovation Seminar",
            "category": "Seminar",
            "date": "Monthly Special Session",
            "venue": "ELH Tech Lab, Pathari",
            "desc": "Hands-on demo of generative AI, robotics engineering, and how high schoolers can build smart IoT devices today.",
            "status": "Registration Open"
        },
        {
            "id": 3,
            "title": "Hands-on IoT Prototype Hackathon",
            "category": "Workshop",
            "date": "Quarterly Event",
            "venue": "ELH Hardware Lab",
            "desc": "A 1-day challenge where student teams assemble and program an environmental sensor network using ESP32 kits.",
            "status": "Scheduled"
        },
        {
            "id": 4,
            "title": "Academic Field Tours & Counseling",
            "category": "Field Tour",
            "date": "Seasonal",
            "venue": "Regional Innovation Centers",
            "desc": "Inspiring excursions to engineering campuses and tech enterprises to expand career horizons for secondary students.",
            "status": "Upcoming"
        }
    ],
    "testimonials": [
        {
            "id": 1,
            "student_name": "Aayush Khatiwada",
            "course": "SEE Master Class (Grade 10)",
            "achievement": "GPA 3.95 (A+)",
            "quote": "The concept-based teaching at ELH made Math and Science crystal clear. The weekly model tests gave me supreme confidence for the board examination.",
            "avatar": "AK"
        },
        {
            "id": 2,
            "student_name": "Sujan Subedi",
            "course": "Tech & IoT Mentorship",
            "achievement": "Smart Home Prototype Winner",
            "quote": "Building live ESP32 projects while still in high school was unimaginable before joining Expert Learning Hub. The lab mentoring is unmatched!",
            "avatar": "SS"
        },
        {
            "id": 3,
            "student_name": "Pooja Dahal",
            "course": "Korean EPS-TOPIK",
            "achievement": "Point System Cleared",
            "quote": "Structured grammar practice, listening labs, and constant motivation helped me crack the EPS exam on my very first attempt!",
            "avatar": "PD"
        }
    ],
    "faqs": [
        {
            "id": 1,
            "question": "Where is Expert Learning Hub located?",
            "answer": "We are centrally located at Expert Tower, Shikar Chowk, Pathari Shanishchare-1, Morang, Nepal.",
            "category": "General"
        },
        {
            "id": 2,
            "question": "What grades do you provide academic coaching for?",
            "answer": "We offer specialized coaching for Grade 8 (BLE), Grade 9, Grade 10 (SEE Master Class), and +2 Science and Commerce programs.",
            "category": "Academic"
        },
        {
            "id": 3,
            "question": "What is included in the Tech & IoT Mentorship program?",
            "answer": "Students work hands-on with microcontrollers (ESP32/Arduino), sensors, actuators, and cloud dashboards to construct complete functional IoT prototypes.",
            "category": "Tech"
        },
        {
            "id": 4,
            "question": "How can I enroll or book a counseling session?",
            "answer": "You can submit the online admission inquiry form directly on this website, call us at +977 9800924090, or visit our Pathari campus directly.",
            "category": "Admission"
        }
    ]
}


class CmsService:
    """Service to manage public website content, sections, and admission leads."""

    def __init__(self, db):
        self.db = db
        self.ensure_defaults()

    def ensure_defaults(self) -> None:
        """Seed default content for sections if not yet present."""
        try:
            existing_rows = self.db.query("SELECT section_key FROM website_cms")
            existing_keys = {row["section_key"] for row in existing_rows}
        except Exception:
            existing_keys = set()

        for key, default_data in DEFAULT_CMS_SECTIONS.items():
            if key not in existing_keys:
                title = key.replace("_", " ").title()
                json_str = json.dumps(default_data, ensure_ascii=False)
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    self.db.execute(
                        "INSERT INTO website_cms (section_key, section_title, content_json, updated_at, updated_by) "
                        "VALUES (?, ?, ?, ?, 'system')",
                        (key, title, json_str, now_str)
                    )
                except Exception:
                    pass

    def get_all_content(self) -> dict[str, Any]:
        """Return all website CMS sections parsed into a single dictionary."""
        result: dict[str, Any] = {}
        try:
            rows = self.db.query("SELECT section_key, content_json FROM website_cms")
            for row in rows:
                key = row["section_key"]
                try:
                    result[key] = json.loads(row["content_json"])
                except Exception:
                    result[key] = DEFAULT_CMS_SECTIONS.get(key, {})
        except Exception:
            pass

        # Fallback any missing sections to default
        for key, default_data in DEFAULT_CMS_SECTIONS.items():
            if key not in result:
                result[key] = default_data
        return result

    def get_section(self, section_key: str) -> Any:
        """Retrieve a specific section's data."""
        try:
            row = self.db.query_one("SELECT content_json FROM website_cms WHERE section_key = ?", (section_key,))
            if row and row["content_json"]:
                return json.loads(row["content_json"])
        except Exception:
            pass
        return DEFAULT_CMS_SECTIONS.get(section_key, {})

    def save_section(self, section_key: str, data: Any, updated_by: str = "admin") -> dict[str, Any]:
        """Save/update a CMS section."""
        title = section_key.replace("_", " ").title()
        json_str = json.dumps(data, ensure_ascii=False)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        row = self.db.query_one("SELECT section_key FROM website_cms WHERE section_key = ?", (section_key,))
        if row:
            self.db.execute(
                "UPDATE website_cms SET content_json = ?, updated_at = ?, updated_by = ? WHERE section_key = ?",
                (json_str, now_str, updated_by, section_key)
            )
        else:
            self.db.execute(
                "INSERT INTO website_cms (section_key, section_title, content_json, updated_at, updated_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (section_key, title, json_str, now_str, updated_by)
            )
        return data

    def reset_defaults(self, updated_by: str = "admin") -> dict[str, Any]:
        """Reset all CMS sections to factory defaults."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for key, default_data in DEFAULT_CMS_SECTIONS.items():
            title = key.replace("_", " ").title()
            json_str = json.dumps(default_data, ensure_ascii=False)
            row = self.db.query_one("SELECT section_key FROM website_cms WHERE section_key = ?", (key,))
            if row:
                self.db.execute(
                    "UPDATE website_cms SET content_json = ?, updated_at = ?, updated_by = ? WHERE section_key = ?",
                    (json_str, now_str, updated_by, key)
                )
            else:
                self.db.execute(
                    "INSERT INTO website_cms (section_key, section_title, content_json, updated_at, updated_by) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (key, title, json_str, now_str, updated_by)
                )
        return self.get_all_content()

    # -------------------------------------------------------------------------
    # Admission Leads & Inquiries
    # -------------------------------------------------------------------------
    def list_inquiries(self, status: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
        """List incoming leads submitted via the public website."""
        query = "SELECT * FROM website_inquiries"
        params = []
        conditions = []
        if status and status != "All":
            conditions.append("status = ?")
            params.append(status)
        if search:
            conditions.append("(full_name LIKE ? OR phone LIKE ? OR course_interest LIKE ?)")
            term = f"%{search.strip()}%"
            params.extend([term, term, term])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id DESC"

        try:
            rows = self.db.query(query, tuple(params))
            return [dict(r) for r in rows]
        except Exception:
            return []

    def create_inquiry(
        self,
        full_name: str,
        phone: str,
        email: str = "",
        grade: str = "",
        course_interest: str = "",
        message: str = "",
    ) -> int:
        """Record a new lead submitted from the website."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.execute(
            "INSERT INTO website_inquiries (full_name, phone, email, grade, course_interest, message, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'New', ?, ?)",
            (full_name.strip(), phone.strip(), (email or "").strip(), (grade or "").strip(), (course_interest or "").strip(), (message or "").strip(), now_str, now_str)
        )
        row = self.db.query_one("SELECT id FROM website_inquiries ORDER BY id DESC LIMIT 1")
        return int(row["id"]) if row else 0

    def update_inquiry(self, inquiry_id: int, status: str, staff_notes: str = "") -> bool:
        """Update inquiry follow-up status and staff notes."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.execute(
            "UPDATE website_inquiries SET status = ?, staff_notes = ?, updated_at = ? WHERE id = ?",
            (status, staff_notes, now_str, inquiry_id)
        )
        return True

    def delete_inquiry(self, inquiry_id: int) -> bool:
        """Delete an inquiry record."""
        self.db.execute("DELETE FROM website_inquiries WHERE id = ?", (inquiry_id,))
        return True
