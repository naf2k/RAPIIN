# ADR-001 — Konsep Deployment RAPIIN: Hybrid Terpusat, bukan Self-Host per User

- **Status:** Accepted
- **Tanggal:** 2026-09-26
- **Konteks keputusan:** Kebingungan memilih antara (A) konsep RAPIIN sekarang
  (core terpusat + Desktop Agent tipis) vs (B) konsep ala OpenClaw/Hermes
  (tiap user install sendiri + bawa API key).

## Keputusan

**Pertahankan konsep hybrid yang sudah ada.** Ini bukan pilihan antara dua
arsitektur, melainkan **pilihan packaging** dari satu codebase yang sama.

- **Arsitektur (tetap):** server = otak (reasoning, AI gateway, DB, audit,
  approval, supervisor); Desktop Agent = tangan (operasi filesystem lokal,
  tidak memegang API key).
- **AI layer: decoupled.** OpenAI-compatible; ganti model = ubah env, nol kode.

## Packaging (dua mode, satu codebase)

1. **Centralized deploy** — server + DB + queue + AI gateway di infra
   organisasi; agent di laptop karyawan. Mendukung supervisor, audit,
   isolasi multi-user.
2. **Local / Desktop Edition** — server + worker + UI + agent di satu mesin,
   single-user, BYOK. Dipakai bila integrasi server belum tersedia.

## Alasan menolak konsep self-host penuh (OpenClaw/Hermes-style)

- Nilai inti RAPIIN (supervisor, audit, approval, isolasi user) hilang bila
  tiap user self-host.
- Target pengguna adalah karyawan kantor non-teknis, bukan power-user personal.
- PRD menyatakan multi-organization SaaS dan kompleksitas serupa
  out-of-scope untuk V1; self-host penuh melangkah lebih jauh dari itu.

## Konsekuensi

- V1 dapat dirilis sebagai **Local/Desktop Edition** tanpa menunggu kepastian
  server, sambil menjaga jalur centralized tetap hidup.
- Pemilihan model AI tidak lagi menjadi blocker: remote OpenAI-compatible
  (mis. `deepseek-v4-flash` untuk produksi; model gratis sebagai fallback).
- Jika server + GPU tersedia kelak, opsi LLM lokal hanya memerlukan perubahan
  `AI_BASE_URL`, tanpa perubahan arsitektur.
- Yang **tidak** dilakukan: instalasi per-user berbasis terminal dengan API key
  masing-masing sebagai konsep produk utama.
