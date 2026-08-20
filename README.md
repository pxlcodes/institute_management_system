# ELH Management System

The application is organized so presentation code can be replaced without rewriting configuration, validation, settings, or health logic.

```text
main.py                    Official application entry point
elh_management_system.py   Compatibility import for older launch scripts
elh/
  config.py                typed environment configuration
  models/                  student, staff, accounting, attendance, receipt and certificate models
  repositories/            persistence interfaces and SQL repositories
  services/                business use cases and dependency container
  core/                    validation, health and settings helpers
  infrastructure/          MySQL and other external persistence adapters
  hardware/
    attendance/            optional ZKTeco adapter
    printing/              optional network ESC/POS adapter
  ui/
    admin.py               separate administration window
    desktop/app.py         Tkinter presentation adapter
.env.example               supported deployment options
tests/                     core tests
```

## Run

Python 3.10 or newer is required. Install the database and PDF dependencies before first use.

```powershell
Copy-Item .env.example .env
python main.py
```

Configuration precedence is: built-in defaults, `.env`, then process environment variables. Relative database and backup paths are resolved from the project/application directory. Do not commit `.env` when it contains deployment-specific values.

Install database dependencies once:

```powershell
python -m pip install -r requirements.txt
```

For MySQL, set `ELH_DATABASE_ENGINE=mysql` together with `ELH_DATABASE_HOST`, `ELH_DATABASE_PORT`, `ELH_DATABASE_NAME`, `ELH_DATABASE_USER`, and `ELH_DATABASE_PASSWORD`. The application creates any missing tables in the selected database during startup. Keep credentials in `.env`; never add them to `.env.example`.

Open **System Admin** in the sidebar for:

- database integrity, migration, storage, logging, configuration, backup, and device health;
- editable `.env` deployment constraints;
- database-backed runtime settings.

Unexpected startup and UI errors are written to rotating files under `logs/`. The UI shows
the log location instead of failing silently. An authenticated session locks automatically
after `ELH_SESSION_IDLE_MINUTES` of inactivity; set the value to `0` only when automatic
locking is intentionally disabled.

## Backup and recovery

**File → Backup Database** creates a consistent SQLite or MySQL backup and a matching
SHA-256 checksum file. MySQL installations are detected automatically from the normal
MySQL Server and Workbench locations; non-standard locations can be configured using
`ELH_MYSQL_DUMP_PATH` and `ELH_MYSQL_CLIENT_PATH`.

Restore validates the backup and checksum first, creates a new safety backup of the current
database, restores the selected file, reapplies required schema migrations, and closes the
application so it can be restarted cleanly. Keep a second encrypted copy of backups away
from the application computer.

## Student and course administration

- The sidebar is grouped into Overview, Students & Courses, Master Data, Staff & Payroll, and Finance.
- Manage reusable course definitions under **Master Data → Courses**. Initial options are Tuition Course Complete, Tuition Monthly, and Korean Language.
- Manage schools independently under **Master Data → Schools**; student forms select from this master list.
- Students, enrollments, and courses support CSV import and export from their respective pages.
- Student entry keeps only the everyday fields on **Quick Entry**. Gender, date of birth,
  guardian relationship, attendance mapping, and the optional student photo are grouped under
  **Additional Details & Photo** and can be completed later by double-clicking the student.
- Student photos are resized before being stored with the student record in the database, so
  normal database backups include them. CSV import/export covers profile text fields but not photos.
- Double-click a student, enrollment, course, or school record to edit it in a separate window.
- Date-labelled fields use the built-in calendar picker. Status fields use radio buttons.
- Business dates use Nepal's Bikram Sambat calendar in `YYYY/MM/DD` format; billing and salary periods use `YYYY/MM`. MySQL technical audit timestamps remain server timestamps.
- Course records own their default instructor. Company Details owns the Principal / Director
  name, so certificate issuance no longer asks for these repeated values.

## SMS notifications

The application can send transactional SMS after student registration, course enrollment,
due-bill generation, bill payment, and certificate issuance. Open **System Admin -> SMS &
Notifications** to select Aakash SMS or Sparrow SMS, enable individual events, edit message
templates, send a test message, review delivery history, and retry a failed delivery.

To resend historical messages manually, select a student under **Student Records** and choose
**Send SMS...**. The dialog lists that student's registration, enrollments, bills, payments, and
certificates; one or several events can be queued together. Manual sends are explicit and can use
the saved templates even while automatic event notifications are disabled.

Provider tokens are secrets and remain in `.env`:

```env
ELH_AAKASH_SMS_TOKEN=
ELH_AAKASH_SMS_ENDPOINT=https://sms.aakashsms.com/sms/v3/send
ELH_SPARROW_SMS_TOKEN=
ELH_SPARROW_SMS_ENDPOINT=https://api.sparrowsms.com/v2/sms/
```

The Sparrow sender identity is non-secret business configuration and is stored under the SMS
settings tab. Automatic SMS is disabled by default. Messages are first written to
`sms_delivery_log` and sent in a background worker; an unavailable gateway cannot roll back a
registration, bill, payment, or certificate. Missing/invalid mobile numbers appear as
**Skipped**, gateway errors as **Failed**, and accepted messages as **Sent**.

Only the placeholders listed beside each event template may be used. This prevents a spelling
mistake in a template from breaking an operational transaction.

## Due bills

Open **Students & Courses → Due Bills** to generate a bill for an active enrollment and billing period. The database permits only one bill for each enrollment-period combination, so repeating generation returns the existing bill. The first bill includes the admission fee and enrollment discount; later bills use the recurring course fee.

Use **Generate Multiple...** to select several enrollments with Ctrl/Shift, or use **Select All**, then enter a start and end month. The system generates one combined bill per selected student enrollment covering all unbilled months in the inclusive range. Individual month items prevent the same month from being billed again when later ranges overlap.

Selected bills can be generated as A4 PDFs, sent through the Windows normal-printer action, or printed as compact receipts through the configured network ESC/POS printer. Generated PDFs are recorded against the bill and saved under `output/pdf/`.

The bill table supports Ctrl/Shift multi-selection and **Select All Bills**. Selected bills can be combined into one batch PDF with two bills per A4 page for a normal printer, or sent sequentially to the POS printer.

POS receipts label the learner as **Student**, print the due date before the tear-off, omit the discount line when the discount is zero, and feed additional blank paper before issuing the cut command.

## Course completion certificates

Open **Students & Courses -> Certificates** to issue a print-ready A4-landscape PDF directly
from the application. Only enrollments marked **Completed** with an end date are offered. Each
enrollment can receive only one certificate, preventing accidental duplicates while allowing
the saved PDF to be opened, printed, or regenerated later. PDF generation does not require
Microsoft Word or a DOCX-to-PDF converter.

The certificate keeps a historical snapshot of the student, guardian, course, company,
course period, instructor, principal, and issue date. Course duration uses the configured
course months at 30 days per month, or the actual Nepali date interval when no duration is
configured. Generated PDFs and optional editable Word files are saved under
`output/certificates/` by default. A SHA-256 checksum is retained with every generated PDF.

When a student photo is available in Student Records, it is placed on the PDF automatically.
The PDF title, accent color, photo visibility, guardian visibility, and date-of-birth visibility
can be changed under **System Administration -> Application Settings -> Certificates**.

Set each course's instructor under **Courses**, the principal under **Company Details**, and the
certificate number prefix under **Application Settings**. File-system choices such as the output
directory and optional replacement `.docx` template remain in `.env`. To place certificate
content over a custom design, export that design as a blank A4-landscape PNG or JPEG and set:

```env
ELH_CERTIFICATE_PDF_BACKGROUND_PATH=templates/my-certificate-background.png
```

The background is presentation-only; the application still draws the live student, course,
date, photo, and signature information directly into the final PDF. The built-in minimal-modern
design is used when the setting is blank.

An editable DOCX remains available as a secondary output. The bundled Word template is included
in the production EXE. Two editable designs are included under `templates/`:
`Certificate_Template_Editable_Fields.docx` retains the original layout, while
`Certificate Template - Minimal Modern.docx` uses only the core completion details.

The supported fields are `{{CERT_NO}}`, `{{TITLE}}`, `{{STUDENT}}`, `{{RELATION}}`,
`{{GUARDIAN}}`, `{{DOB}}`, `{{COURSE}}`, `{{COMPANY}}`, `{{OBJECT}}`, `{{POSSESSIVE}}`,
`{{START_DATE}}`, `{{END_DATE}}`, `{{DAYS}}`, `{{CERT_DATE}}`, `{{INSTRUCTOR}}`, and
`{{PRINCIPAL}}`. Keep each field name
unchanged; its font, color, position, surrounding wording, borders, logo, and shapes can be
edited in Word. These fields affect only the optional DOCX output, not the direct PDF.

## Login roles

The login screen appears before the application workspace. Initial accounts are created only when their usernames do not already exist:

- `operator` / `Operator@2025` - Dashboard, Students, Enrollments, Due Bills, and Student Accounts.
- `admin` / `Admin@2025` - complete operational application, backups, and System Administration.
- `maintenance` / `Maintenance@2025` - schema migration, Python cache clearance, and connected-device health checks only.

Initial credentials are controlled by the corresponding `ELH_*_USERNAME` and `ELH_*_PASSWORD` values before first startup. Passwords stored in `app_users` use salted PBKDF2 hashes; MySQL credentials are never used for application login.

Environment settings take effect after restart. Runtime settings take effect as soon as the consuming feature reads them.

## Reuse from a web application

Web handlers should import `elh.config`, `elh.core.validation`, `elh.core.settings`, and `elh.core.health` directly. Those modules have no dependency on Tkinter. The desktop file is a presentation adapter; keep future HTTP routing and serialization in a separate adapter rather than importing UI page classes.

## Database normalization and performance

The canonical schema is normalized to 3NF for current master data:

- students store `school_id`; the school name is joined from `schools`;
- enrollments store `student_id` and `course_id`; names are joined from their master tables;
- due bills store only `enrollment_id` for their student/course relationship;
- due bill items store only `bill_id`; enrollment is reached through the bill.

Monetary values on bills, transactions, and salary payouts remain deliberate historical snapshots. Ledger `source_type/source_id` and attendance `person_type/person_id` remain polymorphic audit references, not duplicate master fields.

Startup and the maintenance migration action apply versioned normalization and workload indexes. Bulk imports, attendance synchronization, dashboard balances, and multi-student bill generation use set-based or batched queries to avoid per-row database calls.

Business configuration that operators may change—currency, certificate numbering, SMS provider,
sender identity, timeout, enabled events, and message templates—is stored in structured database
tables and included in backups. Machine/deployment values, file paths, database credentials,
hardware endpoints, and SMS API tokens remain in `.env`.

## Payees, vendors, and credit expenses

Use **Finance → Expenses → Manage Payees / Vendors** to register a landlord, supplier/vendor,
staff member, or other payee. These are payee ledgers, not company cash or bank accounts, so a
payment to a landlord or teacher remains correctly visible as an expense while the company account
balance is reduced only once.

- For rent, select the landlord and save the expense as **Paid**. The payee register shows the
  cumulative amount paid to that landlord.
- For a purchase received on credit, select the vendor and save the expense as **Credit**. This
  records the expense and its payable without reducing cash/bank immediately.
- When the supplier is paid, select **Pay Vendor Credit**, choose the real cash/bank account, and
  enter the settlement. The payable balance and company account balance are both updated.
- Staff salary and advance history remains available from **Staff → Staff Payment Summary**,
  while the detailed records remain in **Salary Payouts** and **Staff Advances**.

## Optional hardware

Hardware integrations are disabled by default and cannot prevent normal startup.

For a ZKTeco attendance terminal, install `requirements-hardware.txt`, set `ELH_ATTENDANCE_DRIVER=zkteco`, and configure its host, port, communication password, and timeout. Device user IDs are linked to students or teachers through `device_user_mappings`; synchronized punches are stored in `attendance_logs`.

After importing punches, **Enrollments -> Enroll Today's Present Students** preselects mapped
students who punched today and creates the selected active enrollments in one action. Students
already active in the selected course are skipped. The Dashboard shows today's student presence,
and **Attendance Device -> Student Monthly Totals** shows present days, punches, and attendance
hours for every active student in a Nepali month. Payroll retains attendance as guidance: it can
calculate days/hours and apply an editable pro-rated basic-salary estimate, but it never changes
salary automatically.

For an Ethernet POS printer supporting raw ESC/POS, set `ELH_POS_PRINTER_DRIVER=network_escpos`, its IP address, and normally port `9100`. USB and Windows-spooler printers can be added later by implementing the same `ReceiptPrinter` interface.

Example health endpoint payload:

```python
from elh.config import load_config
from elh.core.health import HealthService

payload = HealthService(load_config()).report()
```

## Verify

```powershell
python -m unittest discover -s tests -v
python -m compileall main.py elh elh_management_system.py
python -m elh.healthcheck
```

The health-check command is read-only: it never creates tables or runs migrations. It exits
with a non-zero status when any check is degraded, making it suitable for deployment scripts
and monitoring.

## First production deployment checklist

Before the first live deployment:

1. Set `ELH_ENVIRONMENT=production` and use a dedicated MySQL account instead of `root`.
   Grant only the rights required on the `elhims` database.
2. Sign in once with each required application account, set unique passwords, then blank the
   three bootstrap password values in `.env`. Continue managing accounts under **Users & Access**.
3. Create a backup from the application, verify the `.sha256` file exists, copy it off this
   computer, and perform a restore drill against a separate test database.
4. Give the attendance device and POS printer reserved/static IP addresses. Confirm device
   health and perform one test attendance sync and one test receipt print.
5. Confirm Nepal time on Windows and MySQL, company/PAN details, opening account balances,
   printer paper width, and the configured Nepali business date.
6. Restrict Windows access to `.env`, `backups/`, and `logs/`; enable disk encryption,
   automatic Windows updates, power protection, and a daily off-machine backup schedule.
7. Run the automated tests and `python -m elh.healthcheck`. Resolve every `ERROR`; review and
   consciously accept or fix every `WARNING` before go-live.
