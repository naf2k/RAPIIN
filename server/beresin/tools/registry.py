"""Tool Gateway - dispatch tool names to local implementations."""
from __future__ import annotations

import json

from ..audit import record_audit
from ..permissions import check_path_allowed, sandbox_root
from . import analysis as analysis_tool
from . import duplicate as duplicate_tool
from . import filesystem as fs_tool
from . import organizer as organizer_tool
from . import verify as verify_tool


def _verification_tool(conn, *, user_id: int, arguments: dict) -> dict:
    operation = arguments.get("operation")
    source = arguments.get("source") or arguments.get("path")
    destination = arguments.get("destination")
    if operation == "move":
        return verify_tool.verify_move(source, destination)
    if operation == "copy":
        return verify_tool.verify_hash(source, destination)
    if operation == "delete":
        return verify_tool.verify_delete(source)
    if operation == "hash":
        return verify_tool.verify_hash(source, destination)
    raise ValueError("Operasi verifikasi harus move, copy, delete, atau hash.")

# Auto (no approval) tools and mutation tools are mapped here.
TOOL_IMPLEMENTATIONS = {
    "filesystem_scanner": fs_tool.scan_directory,
    "metadata_extractor": fs_tool.extract_metadata,
    "file_search": fs_tool.search_files,
    "duplicate_detector": duplicate_tool.find_duplicates,
    "document_parser": analysis_tool.parse_and_summarize,
    "pdf_parser": analysis_tool.parse_and_summarize,
    "spreadsheet_parser": analysis_tool.parse_and_summarize,
    "file_classifier": analysis_tool.classify_folder,
    "semantic_indexer": analysis_tool.index_files,
    "semantic_search": analysis_tool.search_index,
    "folder_organizer": organizer_tool.organize_recommendations,
    "file_move": fs_tool.move_files,
    "file_copy": fs_tool.copy_files,
    "file_rename": fs_tool.rename_files,
    "file_delete": fs_tool.delete_files,
    "batch_executor": fs_tool.execute_batch,
    "bulk_delete": fs_tool.delete_files,
    "verification": _verification_tool,
}

# Tools exposed to the model.
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "filesystem_scanner",
            "description": "Memindai isi sebuah folder dan mengembalikan daftar file beserta metadata dasar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Folder yang ingin dipindai."},
                    "recursive": {"type": "boolean", "description": "Apakah termasuk subfolder."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "metadata_extractor",
            "description": "Mengambil metadata file: nama, ekstensi, ukuran, dan waktu.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_search",
            "description": "Mencari file berdasarkan nama atau ekstensi di dalam folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string"},
                    "query": {"type": "string"},
                    "extension": {"type": "string"},
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "duplicate_detector",
            "description": "Mendeteksi file duplikat persis berdasarkan hash di dalam folder.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_move",
            "description": "Memindahkan satu atau banyak file ke folder tujuan. Membutuhkan persetujuan pengguna.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "destination": {"type": "string"},
                },
                "required": ["destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_copy",
            "description": "Menyalin satu atau banyak file ke folder tujuan. Membutuhkan persetujuan pengguna.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "destination": {"type": "string"},
                },
                "required": ["destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_rename",
            "description": "Mengubah nama file. Membutuhkan persetujuan pengguna.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "new_name": {"type": "string"},
                },
                "required": ["path", "new_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_delete",
            "description": "Menghapus file secara permanen. Membutuhkan persetujuan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "document_parser",
            "description": "Membaca isi satu dokumen (PDF, DOCX, XLSX, PPTX, TXT, CSV) dan mengembalikan ringkasan teksnya.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path file dokumen."}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_parser",
            "description": "Membaca struktur dan teks PDF secara lokal.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spreadsheet_parser",
            "description": "Membaca struktur dan isi XLS/XLSX/CSV secara lokal.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verification",
            "description": "Memverifikasi hasil move, copy, delete, atau kecocokan hash.",
            "parameters": {"type": "object", "properties": {"operation": {"type": "string", "enum": ["move", "copy", "delete", "hash"]}, "source": {"type": "string"}, "destination": {"type": "string"}}, "required": ["operation", "source"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_classifier",
            "description": "Mengelompokkan file dalam folder ke kategori (dokumen, gambar, spreadsheet, dll).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Folder yang akan diklasifikasi."}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_indexer",
            "description": "Mengindeks file dalam folder: hash, metadata, dan pratinjau isi untuk pencarian berikutnya.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Folder yang akan diindeks."}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": "Mencari file yang pernah diindeks berdasarkan nama atau isi teksnya.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Kata kunci pencarian."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "folder_organizer",
            "description": "Menganalisis folder dan menghasilkan rekomendasi penataan terstruktur (folder per jenis, per tahun, hapus duplikat).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Folder yang akan dianalisis."}},
                "required": ["path"],
            },
        },
    },
]


def get_tools_schema() -> list[dict]:
    return list(TOOLS_SCHEMA)


def execute_tool(conn, *, user_id: int, task_id: int | None, device_id: int | None, name: str, arguments: dict) -> dict:
    impl = TOOL_IMPLEMENTATIONS.get(name)
    if not impl:
        raise ValueError(f"Tool tidak dikenal: {name}")

    # Path safety is checked on every mutation tool against the sandbox root.
    if name in {"file_move", "file_copy", "file_rename", "file_delete", "batch_executor", "bulk_delete"}:
        _validate_sandbox(arguments)

    result = impl(conn, user_id=user_id, arguments=arguments)

    record_audit(
        conn,
        actor="BERESIN",
        actor_role="SYSTEM",
        user_id=user_id,
        device_id=device_id,
        action=name,
        resource=_resource_of(arguments),
        task_id=task_id,
        result="SUCCESS" if not result.get("errors") else "PARTIAL",
        error=json.dumps(result["errors"][:3]) if result.get("errors") else None,
    )
    return result


def _resource_of(arguments: dict) -> str | None:
    for key in ("path", "source", "directory", "destination"):
        value = arguments.get(key)
        if value:
            return str(value)
    return None


def _validate_sandbox(arguments: dict) -> None:
    root = sandbox_root()
    for key in ("path", "source", "destination", "new_name"):
        value = arguments.get(key)
        if value and isinstance(value, str):
            allowed, reason = check_path_allowed(root, value)
            if not allowed:
                raise PermissionError(f"Path ditolak kebijakan: {reason}")
    for key in ("paths", "files"):
        values = arguments.get(key) or []
        if isinstance(values, list):
            for value in values:
                allowed, reason = check_path_allowed(root, str(value))
                if not allowed:
                    raise PermissionError(f"Path ditolak kebijakan: {reason}")
