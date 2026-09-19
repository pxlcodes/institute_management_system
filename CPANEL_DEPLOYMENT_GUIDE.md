# ELH Management System - cPanel Deployment & Device Sync Guide

This guide details the end-to-end process of deploying the Expert Learning Hub (ELH) web application to **cPanel hosting** (CloudLinux Phusion Passenger + MySQL) while seamlessly maintaining live synchronization with internal institute hardware (**ZKTeco Biometric Attendance** and **POS Receipt Printer**) via the **Institute Admin PC**.

---

## Architecture Overview

```
                          [ Internet / Outside World ]
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │      cPanel Cloud Host        │
                       │   (portal.yourdomain.com)     │
                       │                               │
                       │  • Python (Passenger WSGI)    │
                       │  • FastAPI Backend            │
                       │  • Vue 3 / Vite Modern SPA    │
                       │  • Central MySQL Database     │
                       │  • Cloud Print Spool Queue    │
                       └───────────────┬───────────────┘
                                       ▲
              HTTPS REST Sync API      │  (Zero Port Forwarding Needed)
            X-Sync-Token Authorized    │  (Bypasses NAT / Dynamic IP)
                                       │
         ══════════════════════════════╪══════════════════════════════
               [ Institute LAN Network (192.168.1.x) ]
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │      Institute Admin PC       │
                       │   (Always Live on LAN)        │
                       │                               │
                       │  • ELH Management System.exe  │
                       │  • elh_device_sync_service.py │
                       └───────┬───────────────┬───────┘
                               │               │
                     TCP 4370  │               │  TCP 9100
             Biometric Punches │               │  Raw ESC/POS
                               ▼               ▼
                       ┌──────────────┐ ┌──────────────┐
                       │    ZKTeco    │ │  POS Printer │
                       │  Biometric   │ │ (192.168.1.36│
                       │ (192.168.1.  │ │   Port 9100) │
                       │     201)     │ └──────────────┘
                       └──────────────┘
```

---

## Part 1: cPanel Server Setup

### Step 1: Create the MySQL Database & User
1. Log into your **cPanel** dashboard.
2. Go to **Databases** -> **MySQL Database Wizard**.
3. Create a new database: e.g. `cpaneluser_elhms`.
4. Create a database user: e.g. `cpaneluser_dbuser` with a strong password.
5. Grant **ALL PRIVILEGES** to the user on this database.
6. *(Optional 1-Click Import)*:
   - Open **phpMyAdmin** from cPanel.
   - Select your newly created database.
   - Click **Import** -> Choose `cpanel_initial_schema.sql` from the release package -> Click **Go**.
   *(Note: If you skip this, ELH will automatically run migrations and create all tables on first startup).*

---

### Step 2: Setup Python Application in cPanel
1. In cPanel, navigate to **Software** -> **Setup Python App**.
2. Click **Create Application**:
   - **Python version**: Select `3.10`, `3.11`, or `3.12`.
   - **Application root**: Path where files will reside, e.g. `portal` or `public_html`.
   - **Application URL**: Select your domain or subdomain (e.g. `portal.yourinstitute.com`).
   - **Application startup file**: `passenger_wsgi.py`
   - **Application Entry point**: `application`
3. Click **Create**.
4. Note the virtual environment activation command displayed at the top of the page (e.g., `source /home/user/virtualenv/portal/3.11/bin/activate`).

---

### Step 3: Upload and Extract Application Files
1. Open cPanel **File Manager**.
2. Navigate to the application root directory configured in Step 2.
3. Upload `elh_cpanel_web_deployment.zip` (from the `release/` folder).
4. Right-click the uploaded ZIP file and click **Extract**.
5. Ensure hidden files (`.htaccess`, `.env.example`) are visible (check **Show Hidden Files** in File Manager Settings).

---

### Step 4: Install Dependencies
1. Open **cPanel Terminal** (or SSH).
2. Activate your application virtual environment:
   ```bash
   source /home/cpaneluser/virtualenv/portal/3.11/bin/activate
   cd /home/cpaneluser/portal
   ```
3. Install the dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements-cpanel.txt
   ```
*(Alternative: On the "Setup Python App" page, type `requirements-cpanel.txt` into the "Configuration files" box and click "Run Pip Install").*

---

### Step 5: Configure `.env` on cPanel
1. In cPanel File Manager inside your application root, copy `.env.example` to `.env`.
2. Edit `.env` and set:
   ```ini
   ELH_APP_TITLE=Expert Learning Hub
   ELH_ENVIRONMENT=production

   # cPanel MySQL database credentials
   ELH_DATABASE_ENGINE=mysql
   ELH_DATABASE_HOST=localhost
   ELH_DATABASE_PORT=3306
   ELH_DATABASE_NAME=cpaneluser_elhms
   ELH_DATABASE_USER=cpaneluser_dbuser
   ELH_DATABASE_PASSWORD=YourStrongDatabasePassword

   # Cloud Device Handling
   ELH_ATTENDANCE_DRIVER=disabled
   ELH_POS_PRINTER_DRIVER=cloud_spool
   ELH_USE_MODERN_WEB=1

   # Security & Device Sync Key
   ELH_SECRET_KEY=CreateA32CharacterRandomSecretStringHere
   ELH_SYNC_API_TOKEN=CreateAUniqueSyncTokenForYourInstituteAdminPC
   ```
3. Save the `.env` file.
4. Back in cPanel **Setup Python App**, click the **Restart** button for your application.
5. Visit your domain in a web browser. You should see the modern ELH Management System portal!

---

## Part 2: Institute Admin PC Setup (Hardware Bridge)

Because the ZKTeco attendance machine and POS printer are inside the institute LAN, the Admin PC functions as the **Institute Device Gateway**.

### Step 1: Configure Admin PC Sync Settings
On the Institute Admin PC, add the cloud connection variables to the project `.env`:
```ini
# Add these lines to connect the Admin PC to your cPanel host:
ELH_CLOUD_URL=https://portal.yourinstitute.com
ELH_SYNC_API_TOKEN=CreateAUniqueSyncTokenForYourInstituteAdminPC

# Keep existing local hardware IP addresses:
ELH_ATTENDANCE_DRIVER=zkteco
ELH_ZKTECO_HOST=192.168.1.201
ELH_ZKTECO_PORT=4370

ELH_POS_PRINTER_DRIVER=network_escpos
ELH_POS_PRINTER_HOST=192.168.1.36
ELH_POS_PRINTER_PORT=9100
```

---

### Step 2: Start the Institute Device Gateway
You have two ways to run the sync gateway:

#### Option A: 1-Click Interactive Runner
Double-click `run_device_sync.bat`.
A terminal window will display:
```text
=========================================================
  ELH Institute Device Gateway - Live Sync Service
=========================================================
Mode: Cloud HTTP Sync (https://portal.yourinstitute.com)
ZKTeco Attendance Device: 192.168.1.201:4370 (Poll every 30s)
ESC/POS Receipt Printer:  192.168.1.36:9100 (Check every 4s)
Running live sync loop...
```
- When staff clicks **"Print POS Bill"** on the cPanel website, the Admin PC receives the print payload and immediately prints the receipt on the physical counter printer!
- Every 30 seconds, all new student and teacher fingerprint/face punches on `192.168.1.201` are automatically uploaded to cPanel!

#### Option B: Automatic Startup on Windows Boot
Right-click `install_device_sync_task.bat` and select **Run as administrator**.
This registers a Windows Scheduled Task (`ELH_Device_Sync`) that starts the service automatically on Windows logon so it runs 24/7 without manual intervention.

---

## Part 3: Desktop Application Usage

The Windows Desktop application (`dist/ELH Management System/ELH Management System.exe` or `release/ELH-Management-System-Windows-x64.zip`) is fully packaged.

- To run against local live database: Launch `ELH Management System.exe` directly.
- To run connected to the remote cPanel database:
  - If cPanel "Remote MySQL" is enabled with the institute's IP whitelisted, configure `.env` with:
    `ELH_DATABASE_HOST=your-cpanel-server-ip`
    `ELH_DATABASE_USER=cpaneluser_dbuser`
    `ELH_DATABASE_PASSWORD=...`
    `ELH_DATABASE_NAME=cpaneluser_elhms`

---

## Verification Checklist

| Test Item | Expected Result | Verified |
|---|---|---|
| cPanel Web URL | Loads ELH login & dashboard with SSL | [ ] |
| Admin Sign-in | Signs in with configured credentials | [ ] |
| Biometric Attendance | `run_device_sync.bat` logs "Attendance push to cloud SUCCESS" | [ ] |
| POS Print Spool | Clicking Print on cPanel triggers physical receipt print on 192.168.1.36 | [ ] |
| Desktop App | `ELH Management System.exe` opens and functions normally | [ ] |
