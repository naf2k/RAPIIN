# PRD — BERESIN

## AI Work Assistant &amp; Intelligent Desktop Agent

**Status:** Draft V1
**Product:** BERESIN
**AI Engine:** Hermes Agent (internal implementation)
**V1 AI Provider:** Configurable OpenAI-compatible AI provider
**Future AI Provider:** Self-hosted Local AI
**Target OS:** Windows-first, extensible to macOS/Linux

---

## 1. Product Overview

BERESIN adalah AI work assistant yang memungkinkan pegawai mengelola pekerjaan digital melalui bahasa natural.

Prinsip utama:

> **User cukup ngomong apa yang ingin dikerjakan. BERESIN memahami, merencanakan, meminta approval bila diperlukan, menjalankan pekerjaan, memverifikasi hasil, lalu menjelaskan hasil secara natural.**

Contoh:

> “Beresin folder Downloads gue.”

BERESIN:

1. Scan folder.
2. Membaca metadata dan isi file yang relevan.
3. Mengelompokkan file.
4. Mendeteksi duplikat.
5. Membuat rekomendasi.
6. Meminta approval.
7. Memindahkan/rename file.
8. Memverifikasi hasil.
9. Melaporkan hasil.

BERESIN bukan sekadar chatbot; ia adalah agent yang dapat memahami konteks, memilih tools, melakukan pekerjaan, dan memverifikasi hasil.

---

## 2. Product Vision

> **Buka BERESIN → ngomong → BERESIN mengerjakan.**

BERESIN harus terasa natural, sederhana, aman, dan tidak membutuhkan user memahami teknologi AI.

---

## 3. Target Users

### Employee / User

Pegawai yang menggunakan BERESIN untuk:

- mengelola file;
- mencari dokumen;
- merapikan folder;
- mengelompokkan dokumen;
- mendeteksi duplikat;
- rename/move/copy file;
- memahami isi dokumen;
- menjalankan pekerjaan digital melalui bahasa natural.

### Supervisor

Supervisor memonitor kesehatan sistem dan aktivitas agent.

V1 menyediakan maksimal **2 akun supervisor**.

Supervisor dapat:

- memonitor user;
- memonitor device;
- memonitor task;
- menangani approval tertentu;
- melihat audit/activity;
- melihat error;
- berinteraksi dengan BERESIN melalui Supervisor Chat.

---

## 4. Core Principle

### Natural Language First — Tool Execution Second

Semua input user masuk ke agent reasoning layer terlebih dahulu.

Jangan membuat sistem berbasis keyword hardcoded seperti:

```
if message == "hai":
    response = "halo"
```

Agent harus memahami intent secara natural.

Contoh:

**Conversation**

> “Halo, lagi ngapain?”

→ Jawab natural, tanpa tool.

**Task**

> “Coba cek folder Downloads gue.”

→ Pahami sebagai filesystem task dan gunakan tool yang sesuai.

**Contextual task**

> “Yang nomor 2 sama 4 gas.”

→ Pahami referensi berdasarkan conversation/task context sebelumnya.

---

# 5. System Architecture

```
                         BERESIN
                    Product Interface
                           │
             ┌─────────────┴─────────────┐
             │                           │
       USER CLIENT                 SUPERVISOR UI
       Chat-first                  Simple Console
             │                           │
          User API                Supervisor API
             │                           │
             └─────────────┬─────────────┘
                           ▼
                    CORE BACKEND
             ┌──────────────────────────┐
             │ Hermes Agent Core        │
             │ Task Engine              │
             │ Tool Gateway             │
             │ Permission Engine        │
             │ Memory                   │
             │ Audit                    │
             │ Device Manager           │
             └────────────┬─────────────┘
                          │
                  ┌───────┴────────┐
                  ▼                ▼
             AI Gateway         Task Queue
                  │
           ┌──────┴──────┐
           ▼             ▼
      Cloud AI API   Future Local AI
                          │
                          ▼
                  Desktop Agents
                          │
              Employee Computers
```

### Prinsip arsitektur

1. Hermes adalah engine di belakang layar.
2. Produk yang dikenal user adalah BERESIN.
3. Hermes Core harus provider-agnostic.
4. User dan Supervisor memiliki interface/API domain berbeda.
5. Core backend tetap menjadi sumber kebenaran bersama.
6. Desktop Agent menjalankan operasi filesystem secara lokal.
7. Server menangani reasoning/orchestration.
8. Semua operasi sensitif melewati permission layer.
9. Semua operasi penting dicatat dalam audit log.
10. Memory user harus terisolasi.
11. Tidak ada unrestricted access ke komputer.

---

# 6. UI/UX SPECIFICATION

## 6.1 General Design Philosophy

BERESIN harus memiliki interface yang **simple, clean, modern, dark, dan mudah dipahami oleh pengguna non-teknis**.

Prioritas utama UI:

1. Mudah dipahami dalam beberapa detik.
2. Tidak membuat user merasa sedang menggunakan software enterprise yang rumit.
3. Informasi penting harus terlihat jelas.
4. Informasi sekunder harus disembunyikan di detail view.
5. Jangan memenuhi layar dengan card, chart, badge, atau statistik yang tidak diperlukan.
6. Interface harus terasa seperti aplikasi AI modern, bukan dashboard administrasi klasik.

### Core UX Principle

> **Complexity belongs in the system, not in the user's interface.**

User tidak perlu memahami:

- Hermes.
- Agent loop.
- Tool calling.
- Task orchestration.
- AI provider.
- Queue.
- File indexing.
- Backend process.

User hanya perlu memahami:

> **"Saya bicara dengan BERESIN, lalu BERESIN mengerjakan."**

---

# 6.2 Visual Direction

Gunakan visual direction berikut:

### Theme

- Dark mode sebagai default.
- Background sangat gelap, tetapi jangan menggunakan pure black secara berlebihan.
- Surface/panel sedikit lebih terang dari background.
- Text utama menggunakan warna off-white.
- Text sekunder menggunakan muted gray.
- Border sangat subtle.
- Gunakan satu accent color utama untuk identitas BERESIN.
- Warna merah hanya untuk error/danger.
- Warna kuning/oranye hanya untuk warning/attention.
- Warna hijau hanya untuk success/healthy.

### Typography

Gunakan font modern dan mudah dibaca.

Hierarchy:

```text
Page Title
    ↓
Section Title
    ↓
Primary Text
    ↓
Secondary Text
    ↓
Metadata

```

Jangan menggunakan terlalu banyak ukuran font.

Text harus cukup besar dan jelas untuk supervisor yang mungkin memiliki keterbatasan visual.

### Spacing

Gunakan spacing yang lega.

Jangan menjejalkan banyak informasi ke dalam satu area.

Prioritaskan:

```text
Clarity > Information Density

```

untuk User UI.

Supervisor UI boleh sedikit lebih information-dense, tetapi tetap mudah dibaca.

### Border &amp; Radius

- Border tipis dan subtle.
- Border digunakan untuk memisahkan area, bukan sebagai dekorasi.
- Gunakan medium corner radius.
- Hindari card dengan radius terlalu besar.
- Hindari glassmorphism berlebihan.

### Icons

Gunakan icon yang sederhana dan konsisten.

Jangan menggunakan emoji sebagai icon UI utama.

Icon harus memiliki fungsi yang jelas.

---

# 6.3 Global UI Rules

OpenCode **WAJIB mengikuti aturan berikut**:

### Jangan membuat:

- Dashboard penuh card.
- 10+ statistic cards.
- Pie chart yang tidak diperlukan.
- Grafik dekoratif.
- Gradient berlebihan.
- Glassmorphism berlebihan.
- Neon effect.
- Excessive shadows.
- Excessive animations.
- Sidebar dengan terlalu banyak menu.
- Floating button yang tidak jelas fungsinya.
- Badge untuk setiap informasi.
- Modal untuk informasi sederhana.
- UI yang terlihat seperti crypto dashboard.
- UI yang terlihat seperti developer monitoring dashboard.

### Jangan menambahkan komponen hanya untuk membuat halaman terlihat penuh.

Jika sebuah informasi tidak penting untuk keputusan user/supervisor, jangan tampilkan di halaman utama.

### Rule:

> **Do not invent unnecessary UI components that are not required by the product requirements.**

---

# 6.4 USER INTERFACE

User interface harus bersifat **chat-first**.

User membuka BERESIN dan langsung melihat conversation interface.

Tidak boleh membuat dashboard sebagai halaman utama user.

## Main Layout

```text
┌──────────────────────────────────────────────────────┐
│ BERESIN                                  ● Online    │
├──────────────┬───────────────────────────────────────┤
│              │                                       │
│  + New Chat  │                                       │
│              │        Conversation Area              │
│  History     │                                       │
│              │                                       │
│  Chat 1      │                                       │
│  Chat 2      │                                       │
│  Chat 3      │                                       │
│              │                                       │
│              │                                       │
│              │                                       │
│              │                                       │
│              │                                       │
│              │ ┌───────────────────────────────────┐ │
│              │ │ Ask BERESIN...                 ↑ │ │
│              │ └───────────────────────────────────┘ │
│              │                                       │
│ Settings     │                                       │
└──────────────┴───────────────────────────────────────┘

```

### Sidebar

Sidebar harus minimal.

Isi:

```text
BERESIN

+ New Chat

Recent Chats
────────────
Chat history
Chat history
Chat history

────────────

Settings

Account

```

Tidak boleh menampilkan:

- analytics;
- system monitoring;
- employee management;
- audit;
- supervisor functions.

User tidak boleh melihat navigation supervisor.

---

# 6.5 User Empty State

Saat belum ada conversation:

```text
              BERESIN

       What can I help you with?

   ┌─────────────────────────────────┐
   │ Ask BERESIN to do something... │
   └─────────────────────────────────┘

```

Tambahkan beberapa contoh prompt sederhana, maksimal 3–4.

Contoh:

```text
"Rapihin folder Downloads gue"
"Cari file laporan bulan lalu"
"Cek file yang duplikat"

```

Jangan membuat 10+ suggestion cards.

---

# 6.6 User Chat Interface

Conversation harus terasa seperti AI assistant modern.

User message:

```text
Rapihin folder Downloads gue.

```

BERESIN:

```text
Bisa. Gue cek dulu isi folder Downloads
dan gue kasih rekomendasinya sebelum
memindahkan file apa pun.

```

Kemudian agent activity dapat ditampilkan secara minimal:

```text
● Scanning Downloads...

```

atau:

```text
● Analyzing 1,248 files...

```

Jangan menampilkan technical logs kepada user.

Jangan menampilkan:

```text
ToolCall(filesystem_scanner)
POST /api/tool/execute
Hermes reasoning...

```

Hal tersebut adalah internal information.

---

# 6.7 Agent Working State

Ketika BERESIN sedang bekerja, user harus mendapatkan feedback bahwa agent masih aktif.

Contoh:

```text
● Checking your files...

```

```text
● Analyzing documents...

```

```text
● Organizing files...

```

Gunakan animasi sederhana dan subtle.

Tidak perlu membuat loading screen penuh.

User harus tetap dapat melihat conversation.

---

# 6.8 File Recommendation UI

Ketika BERESIN menemukan rekomendasi, tampilkan dalam bentuk yang mudah dipahami.

Contoh:

```text
I found 1,248 files.

I recommend:

1. Create folders by document type
   486 files

2. Group documents by year
   391 files

3. Remove exact duplicates
   183 files

Which one would you like me to apply?

```

Jika diperlukan interaction:

```text
[ Apply 1 ]  [ Apply 2 ]  [ Apply 3 ]

```

Jangan menggunakan tabel kompleks jika informasi dapat dijelaskan melalui conversation.

---

# 6.9 Approval UI

Untuk tindakan yang membutuhkan approval:

```text
┌─────────────────────────────────────────┐
│ Action requires your approval           │
│                                         │
│ Delete 183 exact duplicate files        │
│                                         │
│ Files will be permanently removed.      │
│                                         │
│ [ Review ]              [ Cancel ]      │
└─────────────────────────────────────────┘

```

Untuk operasi destructive, tombol harus jelas.

Jangan menyamarkan destructive action.

---

# 6.10 Task Progress

Jika task membutuhkan waktu lama:

```text
Organizing your files...

████████████░░░░  78%

328 / 421 files processed

```

Tampilkan informasi sederhana:

- task name;
- progress;
- processed count;
- current state.

Jangan menampilkan internal implementation details.

---

# 6.11 User Error State

Error harus dijelaskan menggunakan bahasa natural.

Contoh:

> "Gue belum bisa memindahkan 14 file karena folder tujuan tidak punya izin tulis."

Jangan menampilkan stack trace.

Jangan:

```text
Error: EACCES
at fs.rename()
at processTask()
...

```

Technical detail hanya tersedia untuk technical/admin diagnostic interface.

---

# 6.12 User Settings

Settings harus sederhana.

Minimal:

```text
Settings

Account
────────────────
Name
Email

Device
────────────────
PC-ANDI-01
● Connected

Startup
────────────────
☑ Start BERESIN automatically
  when my computer starts

Notifications
────────────────
☑ Task completed
☑ Important errors

About
────────────────
BERESIN version

```

Jangan membuat settings dengan puluhan konfigurasi teknis pada V1.

---

# 6.13 SUPERVISOR INTERFACE

Supervisor memiliki interface yang berbeda dari User.

Supervisor UI bukan chat-first dashboard.

Supervisor UI adalah:

> **Monitor-first, AI-assisted.**

Tujuannya agar supervisor dapat memahami kondisi sistem dengan cepat.

---

# 6.14 Supervisor Main Layout

```text
┌─────────────────────────────────────────────────────────────┐
│ BERESIN                                    Supervisor   👤  │
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│ Overview     │  Overview                                    │
│              │                                              │
│ Tasks        │  System is running normally.                 │
│ Employees    │                                              │
│ Approvals    │  ┌─────────┐ ┌─────────┐ ┌─────────┐        │
│ Activity     │  │ 127     │ │ 12      │ │ 98.7%   │        │
│              │  │ Users   │ │ Tasks   │ │ Success │        │
│              │  └─────────┘ └─────────┘ └─────────┘        │
│              │                                              │
│              │  Needs Attention                             │
│              │                                              │
│              │  ⚠ Dimas — Task failed                      │
│              │  ⚠ 1 approval waiting                       │
│              │                                              │
│              │  Recent Activity                             │
│              │  ✓ Andi completed organization                │
│              │  ✓ Siti completed document scan              │
│              │                                              │
└──────────────┴──────────────────────────────────────────────┘

```

---

# 6.15 Supervisor Sidebar

Sidebar maksimal V1:

```text
BERESIN

Overview

Tasks
Employees
Approvals
Activity

────────────

Settings

Supervisor Account

```

Tidak boleh menambahkan menu lain tanpa requirement yang jelas.

---

# 6.16 Supervisor Overview

Overview harus dapat dipahami dalam sekali lihat.

Maximum primary statistic cards:

**3–4 cards saja.**

Recommended:

```text
Active Users
Running Tasks
Success Rate
System Status

```

Tidak perlu menampilkan 10–20 metrics.

### Needs Attention

Bagian ini harus lebih penting daripada statistik.

Contoh:

```text
Needs Attention

⚠ Dimas
Rename Documents failed

⚠ Bulk delete request
Waiting for supervisor approval

⚠ Device offline
PC-SITI-01

```

Supervisor dapat klik item untuk melihat detail.

---

# 6.17 Supervisor Tasks

Task page harus berupa list/table sederhana.

```text
Tasks

[ All ] [ Running ] [ Waiting ] [ Completed ] [ Failed ]

Search tasks...

────────────────────────────────────────────────────────

User       Task                    Status       Progress
────────────────────────────────────────────────────────

Andi       Organize Documents     Running      78%
Budi       Scan Downloads         Completed    100%
Siti       Find Duplicates        Running      45%
Dimas      Rename Documents       Failed       —

```

Gunakan status text + icon.

Jangan mengandalkan warna saja.

---

# 6.18 Task Detail

Ketika supervisor memilih task:

```text
Organize Documents

User
Andi

Device
PC-ANDI-01

Status
Running

Progress
328 / 421

Started
14:32

Activity

✓ Scanned files
✓ Analyzed documents
✓ Generated recommendation
✓ User approved
● Moving files

```

Technical detail dapat disembunyikan di expandable section jika benar-benar dibutuhkan.

---

# 6.19 Supervisor Employees

Employee page sederhana:

```text
Employees

[ Search employee... ]

──────────────────────────────────────────────

Employee       Device          Status       Tasks

Andi           PC-ANDI-01      ● Online       3
Budi           PC-BUDI-01      ● Online       0
Siti           PC-SITI-01      ○ Offline      -
Dimas          PC-DIMAS-01     ⚠ Warning      1

```

Klik employee untuk detail.

Detail:

- account;
- device;
- connection;
- active task;
- recent activity;
- relevant errors.

Supervisor tidak otomatis dapat melihat isi seluruh file user atau private conversation.

---

# 6.20 Supervisor Approvals

Approval page harus sangat jelas.

```text
Approvals

2 requests waiting

────────────────────────────────────────

Budi
Delete 183 duplicate files

Reason:
Exact duplicate files detected.

Requested:
15:42

[ Review ]


Dimas
Bulk rename 246 files

[ Review ]

```

Detail approval:

```text
Approval Request

User:
Budi

Action:
Delete 183 files

Reason:
Exact duplicates

Scope:
C:\Users\Budi\Downloads\Duplicates

Risk:
Permanent deletion

[ Reject ]     [ Approve ]

```

---

# 6.21 Supervisor Activity

Activity berupa timeline sederhana.

```text
Activity

14:35
✓ Andi completed file organization
   328 files processed

14:34
✓ Budi approved recommendation

14:32
⚠ Dimas task failed
   Permission denied

14:30
✓ Siti started document scan

```

Jangan membuat audit interface seperti raw database table pada halaman utama.

Detail audit dapat dibuka ketika diperlukan.

---

# 6.22 Supervisor Chat

Supervisor memiliki access ke BERESIN melalui chat kecil/command interface.

Contoh:

```text
┌─────────────────────────────────────────┐
│ Ask BERESIN...                       ↑ │
└─────────────────────────────────────────┘

```

Supervisor dapat bertanya:

> "Ada masalah apa hari ini?"

> "Berapa device yang offline?"

> "Task siapa yang paling sering gagal?"

> "Kenapa task Dimas gagal?"

BERESIN menggunakan data monitoring yang authorized.

Supervisor Chat tidak boleh menjadi bypass permission.

---

# 6.23 Responsive Behavior

Desktop adalah target utama.

Untuk window kecil:

- sidebar dapat collapse;
- content tetap readable;
- table dapat berubah menjadi stacked list;
- chat composer tetap accessible.

Jangan membuat interface desktop mengecil secara ekstrem hanya untuk mempertahankan semua elemen.

Prioritaskan readability.

---

# 6.24 Accessibility &amp; Readability

Karena supervisor dapat terdiri dari user non-teknis dan pengguna dengan keterbatasan visual:

- text harus readable;
- contrast harus tinggi;
- click target cukup besar;
- jangan menggunakan font terlalu kecil;
- jangan menggunakan informasi yang hanya dibedakan dengan warna;
- status harus memiliki icon/text;
- error harus jelas;
- destructive action harus mudah dibedakan.

Prioritas:

> **Readable &gt; Fancy**

---

# 6.25 Animation

Animation hanya digunakan untuk:

- loading;
- agent working;
- progress;
- subtle page transition;
- notification.

Animation harus:

- cepat;
- subtle;
- tidak mengganggu;
- tidak terus-menerus bergerak tanpa alasan.

Dilarang:

- excessive particles;
- neon animation;
- animated backgrounds;
- bouncing UI;
- excessive hover effects.

---

# 6.26 UI States

Setiap halaman penting harus memiliki:

### Loading

Menunjukkan data sedang dimuat.

### Empty

Menjelaskan bahwa belum ada data.

### Error

Menjelaskan masalah secara understandable.

### Success

Menunjukkan operasi berhasil.

### Offline

Menunjukkan koneksi/device offline dengan jelas.

Jangan membuat halaman kosong tanpa penjelasan.

---

# 6.27 Design Quality Requirements

OpenCode harus memastikan UI terasa seperti **produk yang benar-benar siap digunakan**, bukan sekadar kumpulan komponen.

Prioritas:

```text
1. Layout hierarchy
2. Readability
3. Consistency
4. Spacing
5. Typography
6. Interaction clarity
7. Visual polish

```

Jangan mengejar visual yang terlalu kompleks.

---

# 6.28 UI Anti-Pattern

Implementasi dianggap tidak sesuai apabila menghasilkan:

- terlalu banyak cards;
- terlalu banyak sidebar menu;
- dashboard penuh grafik;
- font terlalu kecil;
- terlalu banyak warna;
- terlalu banyak badge;
- excessive gradient;
- excessive glassmorphism;
- excessive animation;
- UI terlalu teknis;
- UI seperti monitoring server;
- UI seperti crypto trading dashboard;
- UI seperti template admin generik.

### Final Rule

> **BERESIN harus terlihat sederhana ketika digunakan, walaupun sistem di belakangnya sangat kompleks.**

Jika terdapat konflik antara menampilkan lebih banyak informasi dan menjaga kesederhanaan UI, prioritaskan **kesederhanaan dan readability**, lalu pindahkan informasi tambahan ke detail view.

---

# 7. Authentication &amp; Roles

Minimal role:

```
USER
SUPERVISOR
```

V1:

- maksimal 2 akun supervisor;
- user dapat dibuat sesuai kebutuhan;
- role disimpan pada account;
- authorization wajib dilakukan di backend;
- frontend bukan security boundary.

Contoh capability:

**User**

- akses task sendiri;
- akses device sendiri;
- akses capability yang diizinkan;
- tidak dapat melihat user lain;
- tidak dapat mengakses supervisor API.

**Supervisor**

- monitor user;
- monitor device;
- monitor task;
- melihat audit;
- menangani approval;
- mengelola policy yang diizinkan.

---

# 8. Desktop Agent

Desktop Agent di-install pada komputer user.

Tanggung jawab:

- filesystem scanning;
- metadata extraction;
- document parsing;
- local indexing;
- hashing;
- duplicate detection;
- move;
- copy;
- rename;
- delete sesuai policy;
- verification;
- secure server communication;
- heartbeat;
- reconnect;
- local permission enforcement;
- cache.

Desktop Agent tidak boleh menyediakan unrestricted remote shell atau arbitrary system access.

---

# 9. Installation &amp; CLI

Instalasi dilakukan melalui terminal.

Contoh target:

```
npm install -g beresin
```

Kemudian:

```
beresin
```

First-run:

```
Install
  ↓
Run BERESIN
  ↓
Login
  ↓
Register Device
  ↓
Verify Device
  ↓
Choose Startup Mode
  ├── Manual
  └── Auto Start
  ↓
Agent Ready
```

Feedback CLI:

```
✓ Account authenticated
✓ Device registered
✓ Secure connection established
✓ BERESIN Agent ready
```

---

# 10. Startup Modes

## Manual

User menjalankan:

```
beresin
```

Agent aktif secara manual dan tidak otomatis berjalan saat PC boot.

## Auto Start

User memilih:

> Start BERESIN automatically when my computer starts

Agent didaftarkan sebagai background service/startup mechanism sesuai OS.

Flow:

```
PC ON
 ↓
OS starts
 ↓
BERESIN Agent starts
 ↓
Secure reconnect
 ↓
Heartbeat
 ↓
Agent Ready
```

Tidak boleh membuka terminal window secara mengganggu.

Pengaturan dapat diubah dari Settings.

---

# 11. Device Registration

Setiap device memiliki identity unik.

```
User
 └── Device
      ├── Device ID
      ├── Agent Version
      ├── OS
      ├── Status
      ├── Last Heartbeat
      └── Capabilities
```

Server dapat mengetahui:

- online/offline;
- agent version;
- last heartbeat;
- current task;
- connection health.

---

# 12. Natural Language Agent Flow

```
User Message
     ↓
Conversation Context
     ↓
Hermes Agent
     ↓
Intent Understanding
     ↓
Action Required?
   ┌───────┴────────┐
   NO               YES
   │                 │
   ▼                 ▼
Natural Reply      Planning
                     ↓
                Tool Selection
                     ↓
                Permission Check
                     ↓
                Approval Needed?
                 ┌───┴────┐
                YES       NO
                 │         │
                 ▼         ▼
              Approval   Execute
                 │         │
                 └────┬────┘
                      ▼
                   Execute
                      ↓
                  Verify
                      ↓
                Update Context
                      ↓
                Natural Response
```

---

# 13. File Intelligence

BERESIN harus memahami file lebih dari filename.

Data:

- filename;
- extension;
- size;
- created/modified time;
- path;
- file hash;
- extracted text;
- document structure;
- relevant semantic information.

Supported V1:

- PDF;
- DOC/DOCX;
- XLS/XLSX;
- PPT/PPTX;
- TXT;
- CSV;
- common image formats;
- ZIP metadata;
- folders.

Parsing dibuat modular agar format baru mudah ditambahkan.

---

# 14. Intelligent File Organization

Primary V1 use case:

> Mengorganisir ratusan hingga ribuan file.

Flow:

```
Scan
 ↓
Collect metadata
 ↓
Hash/index
 ↓
Extract content
 ↓
Detect duplicates
 ↓
Classify/group
 ↓
Generate recommendations
 ↓
Show recommendation
 ↓
User approval
 ↓
Execute batch operation
 ↓
Verify
 ↓
Report
```

BERESIN tidak boleh melakukan destructive batch operation hanya karena user mengatakan “rapihin” tanpa memahami scope dan policy.

---

# 15. Performance

Prinsip:

- local scanning;
- incremental indexing;
- hash cache;
- extraction cache;
- hanya proses file baru/berubah;
- batch AI processing;
- parallel processing untuk operasi aman;
- jangan mengirim semua raw file ke server;
- reuse analysis yang masih valid.

Initial scan:

```
Full index
```

Scan berikutnya:

```
Detect changes
→ Process only changed/new files
```

Task panjang berjalan asynchronous melalui task queue.

---

# 16. Tool Gateway

Hermes tidak boleh memanggil local capability secara unrestricted.

```
Hermes
 ↓
Tool Gateway
 ↓
Permission Engine
 ↓
Approval Engine
 ↓
Desktop Agent
 ↓
Local Tool
 ↓
Result
 ↓
Verification
```

Tools V1:

```
filesystem_scanner
metadata_extractor
document_parser
spreadsheet_parser
pdf_parser
duplicate_detector
file_classifier
semantic_indexer
file_search
file_move
file_copy
file_rename
file_delete
batch_executor
verification
```

---

# 17. Permission Model

Capabilities:

```
READ_FILES
SCAN_FILES
SEARCH_FILES
MOVE_FILES
COPY_FILES
RENAME_FILES
DELETE_FILES
BULK_OPERATION
```

Contoh policy:

```
Read/analyze      → automatic
Search            → automatic
Rename            → policy controlled
Move              → approval berdasarkan scope
Copy              → policy controlled
Delete            → approval
Bulk Delete       → stronger approval
Protected paths   → blocked
Other users data  → blocked
```

Exact policy configurable.

---

# 18. Approval System

Approval dapat berasal dari:

- User;
- Supervisor untuk operasi tertentu.

Contoh:

```
BERESIN found 183 exact duplicate files.

Recommended:
Delete duplicates and keep newest versions.

[Review]
[Approve]
[Cancel]
```

Jika policy membutuhkan supervisor:

```
Supervisor approval required.

[Approve]
[Reject]
```

Approval harus dicatat di audit.

---

# 19. Memory &amp; Context Isolation

```
Organization
 ├── User A
 │    ├── Device A
 │    ├── Conversation Context
 │    └── Private Memory
 │
 ├── User B
 │    ├── Device B
 │    ├── Conversation Context
 │    └── Private Memory
 │
 └── Supervisor
      └── Supervisor Context
```

User A tidak boleh mendapatkan memory/context User B.

Password, API key, token, dan credentials tidak boleh disimpan sebagai conversational memory biasa.

---

# 20. Supervisor Monitoring

Supervisor V1:

### Overview

- system status;
- active users;
- running tasks;
- success/failure rate;
- attention-required tasks.

### Employees

- user status;
- device status;
- current tasks;
- recent activity.

### Tasks

- running;
- waiting;
- completed;
- failed;
- progress;
- error detail.

### Approvals

- pending requests;
- details;
- approve/reject.

### Activity

- audit trail aktivitas penting.

---

# 21. Supervisor Chat

Supervisor dapat bertanya secara natural:

> “Ada masalah apa hari ini?”

> “Task siapa yang paling sering gagal?”

> “Berapa device yang offline?”

> “Kenapa task Dimas gagal?”

BERESIN mengambil data yang authorized dan menjawab natural.

Supervisor Chat tidak boleh menjadi permission bypass.

---

# 22. Audit Log

Audit event minimal:

```
actor
actor_role
user_id
device_id
action
resource
timestamp
result
error
approval_id
task_id
```

Audit mencatat:

```
WHO
WHAT
WHEN
WHERE
RESULT
```

Audit log harus append-only secara logical dan tidak dapat diubah user biasa.

---

# 23. Task Engine

Task panjang menjadi asynchronous task.

Fields:

```
task_id
user_id
device_id
type
status
progress
created_at
started_at
completed_at
result
error
approval_status
```

Status:

```
PENDING
PLANNING
WAITING_APPROVAL
RUNNING
VERIFYING
COMPLETED
FAILED
CANCELLED
```

---

# 24. AI Provider Abstraction

BERESIN tidak boleh hardcode ke satu provider.

```
AIProvider
 ├── OpenAICompatibleProvider
 ├── LocalProvider
 └── FutureProvider
```

Provider idealnya mendukung:

- chat;
- tool calling;
- structured output;
- context;
- streaming.

V1:

> Configurable OpenAI-compatible API

Future:

> Self-hosted Local AI

Pergantian provider tidak boleh memerlukan redesign Hermes Core.

---

# 25. Backend API Separation

Gunakan domain API:

```
/api/auth/*
/api/user/*
/api/supervisor/*
```

User API dan Supervisor API dipisahkan secara akses/domain, tetapi memakai Core Backend yang sama.

Jangan membuat dua backend penuh yang menduplikasi Hermes Engine, database, memory, dan task engine.

---

# 26. Security Requirements

Wajib:

- secure authentication;
- password hashing;
- token/session security;
- device identity;
- TLS;
- RBAC;
- capability-based permission;
- local permission enforcement;
- server-side authorization;
- audit logging;
- protected path restrictions;
- no arbitrary shell by default;
- no stealth camera/microphone access;
- no credential harvesting;
- no unrestricted cross-user access;
- confirmation for destructive/bulk operations.

---

# 27. Scalability

Components:

```
API Gateway
Auth
User API
Supervisor API
Hermes Core
AI Gateway
Task Queue
Database
Memory Store
Audit Store
Device Manager
Monitoring
```

Scaling:

```
Many users
 ↓
API Gateway
 ↓
Queue
 ↓
Hermes Workers
 ↓
AI Provider
```

Desktop scanning tetap lokal untuk mengurangi network load.

---

# 28. Error Handling

Jika tool gagal:

1. Return structured error.
2. Hermes memahami error.
3. Retry sesuai policy bila aman.
4. Task menjadi FAILED bila tidak terselesaikan.
5. User menerima penjelasan natural.
6. Supervisor dapat melihat incident sesuai permission.
7. Audit event dibuat.

Jangan menampilkan stack trace teknis kepada user biasa.

---

# 29. Verification

BERESIN tidak boleh menganggap task sukses hanya karena tool mengembalikan success.

Contoh move:

```
Requested move
 ↓
Execute move
 ↓
Check source
 ↓
Check destination
 ↓
Check identity/hash jika relevan
 ↓
Mark verified
```

Bulk result:

```
planned_count
executed_count
verified_count
failed_count
```

---

# 30. Observability

Metrics:

- active users;
- online devices;
- running tasks;
- queue length;
- success rate;
- failure rate;
- AI response latency;
- task duration;
- agent heartbeat;
- error frequency.

Supervisor hanya melihat versi yang relevan dan mudah dipahami.

---

# 31. V1 Scope

## Must Have — User

- authentication;
- chat UI;
- natural language;
- Hermes integration;
- Desktop Agent;
- device registration;
- filesystem scan;
- metadata;
- content extraction;
- file organization recommendation;
- approval;
- move/rename/copy;
- verification;
- task tracking;
- memory isolation;
- CLI installation;
- manual startup;
- auto startup.

## Must Have — Supervisor

- 2 supervisor accounts;
- login;
- simple Overview;
- user monitoring;
- device monitoring;
- task monitoring;
- approval center;
- activity/audit;
- Supervisor Chat.

## Must Have — Infrastructure

- User/Supervisor API separation;
- Core Backend;
- AI provider abstraction;
- configurable OpenAI-compatible provider integration;
- queue;
- database;
- permission engine;
- audit;
- security baseline.

---

# 32. Explicitly Out of Scope V1

- complex analytics dashboard;
- dozens of roles;
- arbitrary remote shell;
- camera/microphone surveillance;
- keylogging;
- hidden monitoring;
- private chat reading;
- credential harvesting;
- multi-organization SaaS management;
- destructive autonomous actions without approval/policy;
- complex workflow builder;
- mobile application.

---

# 33. Development Phases

## Phase 1 — Foundation

Repository, backend, auth, roles, database, AI abstraction, compatible provider, Hermes integration, API.

## Phase 2 — Desktop Agent

CLI package, login, device registration, secure communication, heartbeat, manual startup, auto-start service, local permission layer.

## Phase 3 — File Intelligence

Scanner, metadata, parsers, hashing, indexing, cache, duplicate detection, classification.

## Phase 4 — Agent Execution

Tool Gateway, Permission Engine, planning, approval, file operations, batch executor, verification.

## Phase 5 — User UI

Chat UI, history, task status, approval UI, activity indicator, settings, startup settings.

## Phase 6 — Supervisor

Supervisor auth, Overview, Employees, Devices, Tasks, Approvals, Activity, Supervisor Chat.

## Phase 7 — Testing

Unit, integration, agent, API, permission, isolation, filesystem, failure/recovery, performance, security.

## Phase 8 — Deployment

Production server, database, queue, AI gateway, monitoring, package distribution, versioning, updates, backup/recovery.

---

# 34. Testing Requirements

### Natural language

- greeting;
- casual conversation;
- ambiguous request;
- contextual reference;
- task request;
- follow-up request.

### Files

- 10 files;
- 100 files;
- 1,000 files;
- duplicates;
- unsupported files;
- corrupted files;
- locked files;
- permission denied;
- large files.

### Security

- user accessing another user’s task;
- user accessing another user’s files;
- user calling supervisor API;
- destructive action without approval;
- supervisor unauthorized access.

### Reliability

- agent disconnect;
- server disconnect;
- network interruption;
- AI provider unavailable;
- task timeout;
- partial batch failure;
- PC restart.

### Startup

- manual startup;
- auto startup;
- disable auto startup;
- reboot;
- reconnect.

---

# 35. Acceptance Criteria

V1 berhasil jika:

1. User dapat install Desktop Agent melalui terminal.
2. User dapat login dan register device.
3. User dapat memilih Manual atau Auto Start.
4. Auto Start menghidupkan agent kembali setelah PC restart.
5. User dapat berinteraksi dengan bahasa natural.
6. Casual conversation tidak memanggil tool tanpa alasan.
7. Task filesystem menghasilkan plan yang dapat dipahami.
8. User dapat approve/reject.
9. Agent dapat menjalankan operasi yang diizinkan.
10. Agent memverifikasi hasil.
11. User dapat melihat task status.
12. Memory antar user terisolasi.
13. User tidak dapat mengakses supervisor capability.
14. Supervisor dapat monitor user/device/task.
15. Supervisor dapat menangani approval sesuai policy.
16. Aktivitas penting tercatat dalam audit.
17. Provider AI kompatibel dapat digunakan untuk chat, streaming, dan tool calling.
18. Provider dapat diganti tanpa redesign Hermes Core.
19. Sistem dapat menangani concurrent devices melalui queue.
20. Tidak ada unrestricted access ke perangkat user.

---

# 36. End-to-End User Flow

```
Install
 ↓
Login
 ↓
Choose startup mode
 ↓
Open BERESIN
 ↓
“Rapihin folder Downloads gue.”
 ↓
BERESIN analyzes
 ↓
Recommendation
 ↓
User approves
 ↓
BERESIN executes
 ↓
BERESIN verifies
 ↓
“Udah beres. 328 file berhasil diorganisir.”
```

# 37. End-to-End Supervisor Flow

```
Login
 ↓
Overview
 ↓
See system status
 ↓
See attention items
 ↓
Open task/user/device
 ↓
Review / approve if needed
 ↓
Ask BERESIN for explanation
 ↓
Monitor result
```

---

# 38. Final Product Principle

> **Complexity belongs in the system, not in the user's interface.**

User tidak perlu mengetahui Hermes, tool calling, agent loop, task orchestration, AI provider, queue, atau indexing.

User cukup tahu:

> **“Gue ngomong → BERESIN yang ngurus.”**

Supervisor cukup tahu:

> **“Gue lihat sistem → gue tahu kalau ada masalah → gue bisa mengambil tindakan.”**

Hermes tetap menjadi engine di belakang layar dan tidak menjadi bagian dari product branding.
