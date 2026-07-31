from __future__ import annotations

import os
import queue
import subprocess
import tkinter as tk
from io import BytesIO
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox
from typing import Any

import customtkinter as ctk
from PIL import Image
from tkinterdnd2 import DND_FILES, TkinterDnD

from app.models.app_settings import AppSettings
from app.models.export_result import (
    ExportOptions,
    ExportProgress,
    ExportResult,
)
from app.models.prepared_document import DocumentLoadResult, DocumentSummary
from app.services.document_service import (
    build_document_load_result,
    export_prepared_document,
    prepare_document,
)
from app.services.settings_store import SettingsStore
from app.ui.app_state import (
    FormValidationError,
    UiMode,
    build_export_options,
    derive_output_format_state,
    estimate_slice_outputs,
    parse_hex_rgb,
)
from app.ui.task_runner import (
    Cancelled,
    Failed,
    Progress,
    Started,
    Succeeded,
    TaskEvent,
    TaskRunner,
)


_PHASE_TEXT = {
    "preparing": "正在校验源文件…",
    "parsing": "正在读取切片信息…",
    "reading_composite": "正在解码 Photoshop 合成图…",
    "photoshop": "正在等待 Photoshop 完成高保真渲染…",
    "resizing": "正在统一缩放完整画布…",
    "starting": "正在创建安全输出目录…",
    "exporting": "正在导出切片…",
    "written": "切片已写入并验证",
    "validating": "正在生成验证报告…",
    "archiving": "正在创建 ZIP 压缩包…",
}

_COMPOSITE_TEXT = {
    "embedded_merged": "内嵌高保真合成图",
    "embedded_merged_unverified": "内嵌合成图（未验证）",
    "photoshop": "Photoshop 临时副本渲染",
    "missing": "缺少合成图",
    "invalid": "合成图不可用",
}

_FORMAT_TO_LABEL = {"png": "PNG", "jpeg": "JPEG"}
_LABEL_TO_FORMAT = {value: key for key, value in _FORMAT_TO_LABEL.items()}
_COLOR_TO_LABEL = {
    "auto": "自动",
    "preserve": "保留文档色彩",
    "srgb": "转换为 sRGB",
}
_LABEL_TO_COLOR = {value: key for key, value in _COLOR_TO_LABEL.items()}
_NAMING_TO_LABEL = {
    "sequence_dimensions": "序号 + 尺寸",
    "slice_name": "切片名 + 尺寸",
    "slice_name_with_index": "序号 + 切片名 + 尺寸",
}
_LABEL_TO_NAMING = {
    value: key for key, value in _NAMING_TO_LABEL.items()
}
_PHOTOSHOP_TO_LABEL = {
    "disabled": "禁用",
    "if_needed": "合成图不可用时",
    "always": "总是使用 Photoshop",
}
_LABEL_TO_PHOTOSHOP = {
    value: key for key, value in _PHOTOSHOP_TO_LABEL.items()
}


def parse_hex_color(value: str) -> tuple[int, int, int]:
    try:
        return parse_hex_rgb(value)
    except FormValidationError as error:
        raise ValueError("JPEG 背景色必须是 #RRGGBB 格式。") from error


def parse_drop_paths(tk_app: tk.Misc, raw_data: str) -> tuple[Path, ...]:
    """Decode Tk's Tcl-list drag payload, including paths with spaces."""

    return tuple(Path(item) for item in tk_app.tk.splitlist(raw_data))


def open_in_file_manager(path: Path) -> None:
    target = path if path.is_dir() else path.parent
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(target)])


def open_file(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    subprocess.Popen(["xdg-open", str(path)])


class MainWindow(ctk.CTk):
    """Responsive CustomTkinter front end for the slice export pipeline."""

    _EVENT_POLL_MS = 50
    _MAX_EVENTS_PER_POLL = 40

    def __init__(
        self,
        *,
        settings_store: SettingsStore | None = None,
        task_runner: TaskRunner | None = None,
    ) -> None:
        super().__init__()
        self.title("PSD / PSB 高保真切片导出器")
        self.geometry("1240x820")
        self.minsize(1080, 720)

        self._settings_store = settings_store or SettingsStore()
        settings_result = self._settings_store.load_with_diagnostics()
        self._settings = settings_result.settings
        self._runner = task_runner or TaskRunner(
            load_handler=prepare_document,
            export_handler=export_prepared_document,
            session_result=build_document_load_result,
        )
        self._active_task_id: int | None = None
        self._active_operation: str | None = None
        self._pending_export_options: ExportOptions | None = None
        self._summary: DocumentSummary | None = None
        self._last_result: ExportResult | None = None
        self._mode = UiMode.EMPTY
        self._closing = False
        self._poll_after_id: str | None = None
        self._preview_image: ctk.CTkImage | None = None
        self._preview_pil: Image.Image | None = None
        self._slice_rows: dict[int, tuple[tk.BooleanVar, ctk.CTkLabel]] = {}

        self._create_variables(self._settings)
        self._build_layout()
        self._configure_drag_and_drop()
        self._bind_variable_updates()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_mode("empty")

        if settings_result.warnings:
            self.status_var.set(
                "部分设置已恢复默认值；下次保存时会自动修复。"
            )
        self._schedule_event_poll()

    def _create_variables(self, settings: AppSettings) -> None:
        self.file_var = tk.StringVar(value="尚未选择 PSD / PSB 文件")
        self.document_info_var = tk.StringVar(
            value="画布、色彩模式和切片信息将在加载后显示"
        )
        self.composite_var = tk.StringVar(value="合成图来源：—")
        self.status_var = tk.StringVar(value="请选择或拖入一个文件")
        self.progress_detail_var = tk.StringVar(value="")

        self.width_mode_var = tk.StringVar(
            value=(
                "原始宽度"
                if settings.width_mode == "original"
                else "指定宽度"
            )
        )
        self.target_width_var = tk.StringVar(
            value=str(settings.target_width)
        )
        self.allow_upscale_var = tk.BooleanVar(
            value=settings.allow_upscale
        )
        self.format_var = tk.StringVar(
            value=_FORMAT_TO_LABEL[settings.output_format]
        )
        self.jpeg_quality_var = tk.StringVar(
            value=str(settings.jpeg_quality)
        )
        self.jpeg_background_var = tk.StringVar(
            value=settings.jpeg_background
        )
        self.color_policy_var = tk.StringVar(
            value=_COLOR_TO_LABEL[settings.color_policy]
        )
        self.naming_rule_var = tk.StringVar(
            value=_NAMING_TO_LABEL[settings.naming_rule]
        )
        self.output_directory_var = tk.StringVar(
            value=(
                str(settings.output_directory)
                if settings.output_directory is not None
                else ""
            )
        )
        self.create_zip_var = tk.BooleanVar(value=settings.create_zip)
        self.open_output_var = tk.BooleanVar(
            value=settings.open_output_folder
        )
        self.photoshop_fallback_var = tk.StringVar(
            value=_PHOTOSHOP_TO_LABEL[settings.photoshop_fallback]
        )

        # These safety permissions are intentionally never persisted.
        self.photoshop_launch_var = tk.BooleanVar(value=False)
        self.allow_conversion_var = tk.BooleanVar(value=False)
        self.allow_unverified_var = tk.BooleanVar(value=False)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_drop_header()

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, padx=18, pady=(0, 10), sticky="nsew")
        content.grid_columnconfigure(0, weight=3, uniform="content")
        content.grid_columnconfigure(1, weight=2, uniform="content")
        content.grid_rowconfigure(0, weight=1)

        self._build_document_panel(content)
        self._build_settings_panel(content)
        self._build_footer()

    def _build_drop_header(self) -> None:
        self.drop_frame = ctk.CTkFrame(
            self,
            height=88,
            corner_radius=14,
            border_width=1,
        )
        self.drop_frame.grid(
            row=0,
            column=0,
            padx=18,
            pady=18,
            sticky="ew",
        )
        self.drop_frame.grid_columnconfigure(0, weight=1)
        self.drop_frame.grid_propagate(False)

        ctk.CTkLabel(
            self.drop_frame,
            text="拖入 PSD / PSB，或选择文件",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=(13, 0), sticky="w")
        ctk.CTkLabel(
            self.drop_frame,
            textvariable=self.file_var,
            anchor="w",
            text_color=("gray35", "gray70"),
        ).grid(row=1, column=0, padx=18, pady=(1, 12), sticky="ew")
        self.choose_file_button = ctk.CTkButton(
            self.drop_frame,
            text="选择文件",
            width=112,
            command=self._choose_file,
        )
        self.choose_file_button.grid(
            row=0,
            column=1,
            rowspan=2,
            padx=18,
            pady=18,
        )

    def _build_document_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, corner_radius=14)
        panel.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            panel,
            text="文档与切片",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(14, 2), sticky="w")
        ctk.CTkLabel(
            panel,
            textvariable=self.document_info_var,
            anchor="w",
        ).grid(row=1, column=0, padx=16, sticky="ew")
        ctk.CTkLabel(
            panel,
            textvariable=self.composite_var,
            anchor="w",
            text_color=("gray35", "gray70"),
        ).grid(row=2, column=0, padx=16, pady=(0, 8), sticky="ew")

        body = ctk.CTkFrame(panel, fg_color="transparent")
        body.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        preview = ctk.CTkFrame(body, height=205, corner_radius=10)
        preview.grid(row=0, column=0, sticky="ew")
        preview.grid_columnconfigure(0, weight=1)
        preview.grid_rowconfigure(0, weight=1)
        preview.grid_propagate(False)
        self.preview_label = ctk.CTkLabel(
            preview,
            text="加载后显示首张切片预览",
        )
        self.preview_label.grid(row=0, column=0, padx=10, pady=10)

        controls = ctk.CTkFrame(body, fg_color="transparent")
        controls.grid(row=1, column=0, pady=(8, 4), sticky="ew")
        controls.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            controls,
            text="导出切片",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            controls,
            text="全选",
            width=64,
            height=26,
            command=lambda: self._set_all_slices(True),
        ).grid(row=0, column=1, padx=4)
        ctk.CTkButton(
            controls,
            text="全不选",
            width=72,
            height=26,
            fg_color="transparent",
            border_width=1,
            command=lambda: self._set_all_slices(False),
        ).grid(row=0, column=2)

        self.slice_list = ctk.CTkScrollableFrame(
            body,
            corner_radius=10,
            label_text="序号 / 名称 · 坐标 · 原始尺寸 → 输出尺寸",
            label_anchor="w",
        )
        self.slice_list.grid(row=2, column=0, sticky="nsew")
        self.slice_list.grid_columnconfigure(0, weight=1)

    def _build_settings_panel(self, parent: ctk.CTkFrame) -> None:
        self.settings_panel = ctk.CTkScrollableFrame(
            parent,
            corner_radius=14,
            label_text="导出设置",
            label_font=ctk.CTkFont(size=17, weight="bold"),
            label_anchor="w",
        )
        self.settings_panel.grid(
            row=0,
            column=1,
            padx=(8, 0),
            sticky="nsew",
        )
        self.settings_panel.grid_columnconfigure(0, weight=1)
        row = 0

        self.width_segment = ctk.CTkSegmentedButton(
            self.settings_panel,
            values=["原始宽度", "指定宽度"],
            variable=self.width_mode_var,
            command=lambda _: self._on_form_change(),
        )
        self.width_segment.grid(
            row=row,
            column=0,
            padx=12,
            pady=(6, 8),
            sticky="ew",
        )
        row += 1

        width_row = ctk.CTkFrame(
            self.settings_panel,
            fg_color="transparent",
        )
        width_row.grid(row=row, column=0, padx=12, sticky="ew")
        width_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(width_row, text="目标宽度").grid(
            row=0, column=0, padx=(0, 8)
        )
        self.target_width_entry = ctk.CTkEntry(
            width_row,
            textvariable=self.target_width_var,
            placeholder_text="1440",
        )
        self.target_width_entry.grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(width_row, text="px").grid(
            row=0, column=2, padx=(6, 0)
        )
        row += 1

        self.allow_upscale_switch = ctk.CTkSwitch(
            self.settings_panel,
            text="允许放大（关闭时只允许缩小或原尺寸）",
            variable=self.allow_upscale_var,
            command=self._on_form_change,
        )
        self.allow_upscale_switch.grid(
            row=row, column=0, padx=12, pady=(6, 12), sticky="w"
        )
        row += 1

        ctk.CTkLabel(
            self.settings_panel,
            text="文件格式",
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=row, column=0, padx=12, sticky="ew")
        row += 1
        self.format_segment = ctk.CTkSegmentedButton(
            self.settings_panel,
            values=["PNG", "JPEG"],
            variable=self.format_var,
            command=lambda _: self._on_format_change(),
        )
        self.format_segment.grid(
            row=row, column=0, padx=12, pady=(4, 6), sticky="ew"
        )
        row += 1

        jpeg_row = ctk.CTkFrame(
            self.settings_panel,
            fg_color="transparent",
        )
        jpeg_row.grid(row=row, column=0, padx=12, sticky="ew")
        jpeg_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(jpeg_row, text="JPEG 质量").grid(
            row=0, column=0, padx=(0, 8)
        )
        self.jpeg_quality_entry = ctk.CTkEntry(
            jpeg_row,
            width=70,
            textvariable=self.jpeg_quality_var,
        )
        self.jpeg_quality_entry.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(jpeg_row, text="背景").grid(
            row=0, column=2, padx=(12, 6)
        )
        self.jpeg_background_entry = ctk.CTkEntry(
            jpeg_row,
            width=92,
            textvariable=self.jpeg_background_var,
        )
        self.jpeg_background_entry.grid(row=0, column=3)
        self.color_button = ctk.CTkButton(
            jpeg_row,
            text="…",
            width=32,
            command=self._choose_background_color,
        )
        self.color_button.grid(row=0, column=4, padx=(5, 0))
        row += 1

        self.color_policy_menu = self._labeled_option(
            row,
            "色彩策略",
            self.color_policy_var,
            list(_LABEL_TO_COLOR),
        )
        row += 1
        self.naming_menu = self._labeled_option(
            row,
            "文件命名",
            self.naming_rule_var,
            list(_LABEL_TO_NAMING),
        )
        row += 1

        ctk.CTkLabel(
            self.settings_panel,
            text="Photoshop 高保真回退",
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=row, column=0, padx=12, pady=(14, 0), sticky="ew")
        row += 1
        self.photoshop_menu = ctk.CTkOptionMenu(
            self.settings_panel,
            values=list(_LABEL_TO_PHOTOSHOP),
            variable=self.photoshop_fallback_var,
            command=lambda _: self._on_photoshop_change(),
        )
        self.photoshop_menu.grid(
            row=row, column=0, padx=12, pady=(4, 4), sticky="ew"
        )
        row += 1
        self.photoshop_launch_check = ctk.CTkCheckBox(
            self.settings_panel,
            text="本次允许启动 Photoshop（不会保存此授权）",
            variable=self.photoshop_launch_var,
        )
        self.photoshop_launch_check.grid(
            row=row, column=0, padx=12, pady=4, sticky="w"
        )
        row += 1
        ctk.CTkLabel(
            self.settings_panel,
            text="使用前请保存并关闭 Photoshop 中所有打开的文档。",
            wraplength=360,
            justify="left",
            text_color=("#8A5A00", "#E0B55B"),
        ).grid(row=row, column=0, padx=12, pady=(0, 8), sticky="w")
        row += 1

        ctk.CTkLabel(
            self.settings_panel,
            text="输出目录",
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=row, column=0, padx=12, pady=(8, 0), sticky="ew")
        row += 1
        output_row = ctk.CTkFrame(
            self.settings_panel,
            fg_color="transparent",
        )
        output_row.grid(row=row, column=0, padx=12, pady=4, sticky="ew")
        output_row.grid_columnconfigure(0, weight=1)
        self.output_entry = ctk.CTkEntry(
            output_row,
            textvariable=self.output_directory_var,
            placeholder_text="留空则输出到源文件旁",
        )
        self.output_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            output_row,
            text="浏览",
            width=62,
            command=self._choose_output_directory,
        ).grid(row=0, column=1, padx=(6, 0))
        row += 1

        ctk.CTkCheckBox(
            self.settings_panel,
            text="完成后创建 ZIP",
            variable=self.create_zip_var,
        ).grid(row=row, column=0, padx=12, pady=3, sticky="w")
        row += 1
        ctk.CTkCheckBox(
            self.settings_panel,
            text="完成后打开输出目录",
            variable=self.open_output_var,
        ).grid(row=row, column=0, padx=12, pady=3, sticky="w")
        row += 1

        ctk.CTkLabel(
            self.settings_panel,
            text="当前文档高级授权（不会保存）",
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=row, column=0, padx=12, pady=(14, 2), sticky="ew")
        row += 1
        ctk.CTkCheckBox(
            self.settings_panel,
            text="允许必要的色彩 / 模式转换",
            variable=self.allow_conversion_var,
        ).grid(row=row, column=0, padx=12, pady=3, sticky="w")
        row += 1
        ctk.CTkCheckBox(
            self.settings_panel,
            text="允许使用完整性未验证的内嵌合成图",
            variable=self.allow_unverified_var,
        ).grid(row=row, column=0, padx=12, pady=(3, 12), sticky="w")

        self._on_format_change()
        self._on_photoshop_change()

    def _labeled_option(
        self,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: list[str],
    ) -> ctk.CTkOptionMenu:
        container = ctk.CTkFrame(
            self.settings_panel,
            fg_color="transparent",
        )
        container.grid(row=row, column=0, padx=12, pady=4, sticky="ew")
        container.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(container, text=label).grid(
            row=0, column=0, padx=(0, 8)
        )
        menu = ctk.CTkOptionMenu(
            container,
            values=values,
            variable=variable,
            command=lambda _: self._on_form_change(),
        )
        menu.grid(row=0, column=1, sticky="ew")
        return menu

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, corner_radius=14)
        footer.grid(
            row=2,
            column=0,
            padx=18,
            pady=(0, 18),
            sticky="ew",
        )
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            footer,
            textvariable=self.status_var,
            anchor="w",
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(10, 0), sticky="ew")
        ctk.CTkLabel(
            footer,
            textvariable=self.progress_detail_var,
            anchor="w",
            text_color=("gray35", "gray70"),
        ).grid(row=1, column=0, padx=14, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(footer, height=8)
        self.progress_bar.grid(
            row=2, column=0, padx=14, pady=(6, 12), sticky="ew"
        )
        self.progress_bar.set(0)

        self.open_output_button = ctk.CTkButton(
            footer,
            text="打开输出",
            width=92,
            command=self._open_last_output,
        )
        self.open_output_button.grid(
            row=0, column=1, rowspan=3, padx=(6, 4), pady=12
        )
        self.open_report_button = ctk.CTkButton(
            footer,
            text="查看报告",
            width=92,
            command=self._open_last_report,
        )
        self.open_report_button.grid(
            row=0, column=2, rowspan=3, padx=4, pady=12
        )
        self.cancel_button = ctk.CTkButton(
            footer,
            text="取消",
            width=82,
            fg_color=("#B04A4A", "#9B3B3B"),
            hover_color=("#963A3A", "#842F2F"),
            command=self._cancel_active_task,
        )
        self.cancel_button.grid(
            row=0, column=3, rowspan=3, padx=4, pady=12
        )
        self.export_button = ctk.CTkButton(
            footer,
            text="开始导出",
            width=112,
            command=self._on_export,
        )
        self.export_button.grid(
            row=0, column=4, rowspan=3, padx=(4, 14), pady=12
        )

    def _configure_drag_and_drop(self) -> None:
        try:
            TkinterDnD.require(self)
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            # File selection remains available if a local Tcl/Tk build cannot
            # load the optional tkdnd extension.
            pass

    def _bind_variable_updates(self) -> None:
        for variable in (
            self.target_width_var,
            self.jpeg_quality_var,
            self.jpeg_background_var,
            self.output_directory_var,
        ):
            variable.trace_add("write", lambda *_: self._on_form_change())

    def _choose_file(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="选择 PSD / PSB 文件",
            filetypes=[
                ("Photoshop 文件", "*.psd *.psb"),
                ("PSD", "*.psd"),
                ("PSB", "*.psb"),
                ("所有文件", "*.*"),
            ],
        )
        if selected:
            self._start_load(Path(selected))

    def _on_drop(self, event: Any) -> str:
        paths = parse_drop_paths(self, event.data)
        candidates = [
            path for path in paths if path.suffix.lower() in {".psd", ".psb"}
        ]
        if not candidates:
            messagebox.showwarning(
                "不支持的文件",
                "请拖入 PSD 或 PSB 文件。",
                parent=self,
            )
            return "break"
        self._start_load(candidates[0])
        return "break"

    def _preparation_options(self) -> ExportOptions:
        return ExportOptions(
            photoshop_fallback=_LABEL_TO_PHOTOSHOP[
                self.photoshop_fallback_var.get()
            ],
            photoshop_allow_launch=self.photoshop_launch_var.get(),
            allow_unverified_composite=self.allow_unverified_var.get(),
        )

    def _start_load(
        self,
        path: Path,
        *,
        pending_export: ExportOptions | None = None,
    ) -> None:
        if self._runner.is_running:
            return
        if not path.is_file() or path.suffix.lower() not in {".psd", ".psb"}:
            messagebox.showerror(
                "无法打开",
                "请选择存在的 PSD 或 PSB 文件。",
                parent=self,
            )
            return

        self._summary = None
        self._clear_document_view()
        self.file_var.set(str(path))
        self._pending_export_options = pending_export
        try:
            task_id = self._runner.start_load(
                path,
                self._preparation_options(),
                allow_unavailable=True,
            )
        except Exception as error:
            messagebox.showerror("无法开始加载", str(error), parent=self)
            return
        self._active_task_id = task_id
        self._active_operation = "load"
        self._set_mode("loading")
        self.status_var.set(f"正在加载 {path.name}")
        self.progress_detail_var.set("大尺寸 PSD / PSB 会在后台解析")

    def _on_export(self) -> None:
        try:
            options = self._build_export_options()
        except ValueError as error:
            messagebox.showwarning("请检查设置", str(error), parent=self)
            return
        if self._summary is None:
            return

        self._save_settings_safely()
        if not self._cache_matches_options(options):
            self._start_load(
                self._summary.source_path,
                pending_export=options,
            )
            return
        if not self._summary.composite_is_available:
            messagebox.showerror(
                "合成图不可用",
                (
                    self._summary.composite_error
                    or "请将 Photoshop 回退设为“合成图不可用时”后重试。"
                ),
                parent=self,
            )
            return
        self._start_export(options)

    def _start_export(self, options: ExportOptions) -> None:
        if self._runner.is_running:
            return
        try:
            task_id = self._runner.start_export(options)
        except Exception as error:
            messagebox.showerror("无法开始导出", str(error), parent=self)
            return
        self._active_task_id = task_id
        self._active_operation = "export"
        self._set_mode("exporting")
        self.status_var.set("正在准备导出")
        self.progress_detail_var.set("")
        self._last_result = None

    def _build_export_options(self) -> ExportOptions:
        if self._summary is None:
            raise FormValidationError("请先加载 PSD 或 PSB 文件。")
        settings = self._settings_from_form(strict=True)

        selected = frozenset(
            index
            for index, (variable, _) in self._slice_rows.items()
            if variable.get()
        )
        if not selected:
            raise FormValidationError("请至少选择一张切片。")

        output_text = self.output_directory_var.get().strip()
        return build_export_options(
            settings,
            self._summary,
            output_directory=output_text or None,
            selected_slice_indices=selected,
            photoshop_allow_launch=self.photoshop_launch_var.get(),
            allow_mode_conversion=self.allow_conversion_var.get(),
            allow_unverified_composite=self.allow_unverified_var.get(),
        )

    def _cache_matches_options(self, options: ExportOptions) -> bool:
        if self._summary is None:
            return False
        prepared_mode = self._summary.preparation_mode
        requested_mode = options.photoshop_fallback
        if prepared_mode == requested_mode:
            return True
        return (
            self._summary.composite_source == "embedded_merged"
            and self._summary.composite_is_reliable
            and prepared_mode in {"disabled", "if_needed"}
            and requested_mode in {"disabled", "if_needed"}
        )

    def _cancel_active_task(self) -> None:
        if not self._runner.request_cancel():
            return
        self._set_mode("cancelling")
        self.status_var.set("正在安全取消…")
        self.progress_detail_var.set(
            "当前解析、Photoshop、缩放或压缩步骤结束后会停止"
        )

    def _schedule_event_poll(self) -> None:
        if self._closing:
            return
        self._poll_after_id = self.after(
            self._EVENT_POLL_MS,
            self._drain_worker_events,
        )

    def _drain_worker_events(self) -> None:
        self._poll_after_id = None
        for _ in range(self._MAX_EVENTS_PER_POLL):
            try:
                event = self._runner.events.get_nowait()
            except queue.Empty:
                break
            self._handle_worker_event(event)
        self._schedule_event_poll()

    def _handle_worker_event(self, event: TaskEvent) -> None:
        if event.task_id == 0:
            if isinstance(event, Failed):
                self.status_var.set(f"关闭资源时发生错误：{event.message}")
            return
        if event.task_id != self._active_task_id:
            return
        if isinstance(event, Started):
            return
        if isinstance(event, Progress):
            if isinstance(event.value, ExportProgress):
                self._show_progress(event.value)
            return

        operation = self._active_operation
        self._active_task_id = None
        self._active_operation = None
        self.progress_bar.stop()

        if isinstance(event, Succeeded):
            if operation == "load":
                self._handle_document_loaded(event.result)
            elif operation == "export":
                self._handle_export_finished(event.result)
            return
        if isinstance(event, Cancelled):
            self._handle_cancelled(event, operation)
            return
        if isinstance(event, Failed):
            self._handle_failed(event, operation)

    def _show_progress(self, progress: ExportProgress) -> None:
        phase_text = _PHASE_TEXT.get(progress.phase, progress.phase)
        self.status_var.set(phase_text)
        if progress.total > 0 and progress.phase in {
            "exporting",
            "written",
            "validating",
            "archiving",
        }:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            completed = progress.current
            if progress.phase == "exporting":
                completed = max(0, progress.current - 1)
            self.progress_bar.set(min(1.0, completed / progress.total))
            if progress.slice_info is not None:
                self.progress_detail_var.set(
                    f"切片 {progress.current}/{progress.total} · "
                    f"{progress.slice_info.name or '未命名'}"
                )
            else:
                self.progress_detail_var.set(
                    f"{progress.current}/{progress.total}"
                )
        else:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
            self.progress_detail_var.set(
                "已请求取消，等待当前步骤结束"
                if self._mode == "cancelling"
                else ""
            )

    def _handle_document_loaded(self, result: object) -> None:
        if not isinstance(result, DocumentLoadResult):
            self._show_internal_result_error("加载结果类型不正确。")
            return
        self._summary = result.summary
        self.file_var.set(str(result.summary.source_path))
        alpha_text = "含透明度" if result.summary.has_alpha else "不透明"
        self.document_info_var.set(
            f"{result.summary.width} × {result.summary.height}px · "
            f"{result.summary.color_mode} / {result.summary.depth} 位 · "
            f"{alpha_text} · {result.summary.slice_count} 张切片"
        )
        source_text = _COMPOSITE_TEXT.get(
            result.summary.composite_source,
            result.summary.composite_source,
        )
        self.composite_var.set(f"合成图来源：{source_text}")
        self._populate_slices(result.summary)
        self._set_preview(result.preview_png)
        self.photoshop_launch_var.set(False)
        self._set_mode("ready")
        self.status_var.set(
            f"已加载 {result.summary.source_path.name}"
        )
        warning = (
            result.summary.composite_error
            or result.summary.composite_warning
        )
        self.progress_detail_var.set(warning or "可调整宽度后直接重复导出")

        pending = self._pending_export_options
        self._pending_export_options = None
        if pending is not None:
            self.after_idle(lambda: self._start_export(pending))

    def _handle_export_finished(self, result: object) -> None:
        if not isinstance(result, ExportResult):
            self._show_internal_result_error("导出结果类型不正确。")
            return
        self._last_result = result
        self._set_mode("ready")
        self.progress_bar.set(1)
        if result.status == "completed":
            self.status_var.set(
                f"导出完成：{len(result.exported_slices)} 张切片"
            )
            self.progress_detail_var.set(
                f"{result.output_directory} · {result.elapsed_seconds:.1f} 秒"
            )
            if self.open_output_var.get():
                try:
                    open_in_file_manager(result.output_directory)
                except OSError as error:
                    self.progress_detail_var.set(
                        f"导出成功，但无法打开目录：{error}"
                    )
        else:
            self.status_var.set("导出完成，但验证发现问题")
            self.progress_detail_var.set(
                f"{len(result.failures)} 项失败；请查看验证报告"
            )

    def _handle_cancelled(
        self,
        event: Cancelled[Any],
        operation: str | None,
    ) -> None:
        if isinstance(event.result, ExportResult):
            self._last_result = event.result
            self.status_var.set("导出已取消，已完成的文件保留在输出目录")
            self.progress_detail_var.set(str(event.result.output_directory))
        else:
            self.status_var.set("任务已取消")
            self.progress_detail_var.set(event.message or "")
        self._pending_export_options = None
        self._set_mode("ready" if self._summary is not None else "empty")

    def _handle_failed(
        self,
        event: Failed,
        operation: str | None,
    ) -> None:
        self._pending_export_options = None
        self._set_mode("ready" if self._summary is not None else "empty")
        self.status_var.set("加载失败" if operation == "load" else "导出失败")
        self.progress_detail_var.set(event.message)
        message = event.message or f"{event.exception_type} 未提供说明。"
        if "Photoshop" in message:
            message += (
                "\n\n请确认 Photoshop 已启动，且所有文档都已保存并关闭。"
            )
        messagebox.showerror(
            "任务失败",
            message,
            parent=self,
        )

    def _show_internal_result_error(self, message: str) -> None:
        self._set_mode("empty")
        self.status_var.set(message)
        messagebox.showerror("内部错误", message, parent=self)

    def _populate_slices(self, summary: DocumentSummary) -> None:
        for child in self.slice_list.winfo_children():
            child.destroy()
        self._slice_rows.clear()
        for row_index, item in enumerate(summary.slices):
            row = ctk.CTkFrame(
                self.slice_list,
                fg_color=("gray92", "gray20"),
                corner_radius=7,
            )
            row.grid(
                row=row_index,
                column=0,
                padx=2,
                pady=2,
                sticky="ew",
            )
            row.grid_columnconfigure(1, weight=1)
            selected = tk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                row,
                text="",
                width=28,
                variable=selected,
                command=self._on_form_change,
            ).grid(row=0, column=0, padx=(8, 2), pady=7)
            display_name = item.name.strip() or "未命名"
            ctk.CTkLabel(
                row,
                text=f"{row_index + 1:02d}  {display_name}",
                anchor="w",
            ).grid(row=0, column=1, sticky="ew")
            ctk.CTkLabel(
                row,
                text=f"({item.left}, {item.top})",
                text_color=("gray40", "gray65"),
            ).grid(row=0, column=2, padx=7)
            output_label = ctk.CTkLabel(
                row,
                text=f"{item.width}×{item.height} → —",
                width=180,
                anchor="e",
            )
            output_label.grid(row=0, column=3, padx=(4, 10))
            self._slice_rows[item.index] = (selected, output_label)
        self._refresh_output_dimensions()

    def _set_all_slices(self, selected: bool) -> None:
        for variable, _ in self._slice_rows.values():
            variable.set(selected)
        self._on_form_change()

    def _refresh_output_dimensions(self) -> None:
        summary = self._summary
        if summary is None:
            return
        try:
            target_width = int(self.target_width_var.get().strip())
            sizing_settings = AppSettings(
                width_mode=(
                    "original"
                    if self.width_mode_var.get() == "原始宽度"
                    else "custom"
                ),
                target_width=target_width,
                allow_upscale=self.allow_upscale_var.get(),
            )
            estimates = estimate_slice_outputs(
                sizing_settings,
                summary,
            )
        except (ValueError, FormValidationError):
            for _, label in self._slice_rows.values():
                label.configure(text="输出尺寸无效")
            return
        mapped_by_index = {
            estimate.index: estimate for estimate in estimates
        }
        for item in summary.slices:
            estimate = mapped_by_index[item.index]
            _, label = self._slice_rows[item.index]
            label.configure(
                text=(
                    f"{item.width}×{item.height} → "
                    f"{estimate.output_width}×{estimate.output_height}"
                )
            )

    def _set_preview(self, png_bytes: bytes | None) -> None:
        if self._preview_pil is not None:
            self._preview_pil.close()
            self._preview_pil = None
        self._preview_image = None
        if not png_bytes:
            self.preview_label.configure(
                image=None,
                text="当前合成图无法生成预览",
            )
            return
        with Image.open(BytesIO(png_bytes)) as image:
            image.load()
            self._preview_pil = image.copy()
        size = self._preview_pil.size
        self._preview_image = ctk.CTkImage(
            light_image=self._preview_pil,
            dark_image=self._preview_pil,
            size=size,
        )
        self.preview_label.configure(
            image=self._preview_image,
            text="",
        )

    def _clear_document_view(self) -> None:
        self.document_info_var.set("正在读取文档信息…")
        self.composite_var.set("合成图来源：—")
        for child in self.slice_list.winfo_children():
            child.destroy()
        self._slice_rows.clear()
        self._set_preview(None)

    def _on_form_change(self) -> None:
        if hasattr(self, "target_width_entry"):
            self.target_width_entry.configure(
                state=(
                    "normal"
                    if self.width_mode_var.get() == "指定宽度"
                    else "disabled"
                )
            )
        self._refresh_output_dimensions()
        self._refresh_export_button()

    def _on_format_change(self) -> None:
        format_state = derive_output_format_state(
            _LABEL_TO_FORMAT[self.format_var.get()]
        )
        enabled = format_state.jpeg_quality_enabled
        state = "normal" if enabled else "disabled"
        self.jpeg_quality_entry.configure(state=state)
        self.jpeg_background_entry.configure(state=state)
        self.color_button.configure(state=state)
        self._on_form_change()

    def _on_photoshop_change(self) -> None:
        enabled = (
            _LABEL_TO_PHOTOSHOP[self.photoshop_fallback_var.get()]
            != "disabled"
        )
        self.photoshop_launch_check.configure(
            state="normal" if enabled else "disabled"
        )
        if not enabled:
            self.photoshop_launch_var.set(False)
        self._on_form_change()

    def _choose_background_color(self) -> None:
        _, selected = colorchooser.askcolor(
            color=self.jpeg_background_var.get(),
            parent=self,
            title="选择 JPEG 背景色",
        )
        if selected:
            self.jpeg_background_var.set(selected.upper())

    def _choose_output_directory(self) -> None:
        initial_directory = self.output_directory_var.get()
        if not initial_directory and self._summary is not None:
            initial_directory = str(self._summary.source_path.parent)
        dialog_options: dict[str, object] = {
            "parent": self,
            "title": "选择输出目录",
        }
        if initial_directory:
            dialog_options["initialdir"] = initial_directory
        selected = filedialog.askdirectory(**dialog_options)
        if selected:
            self.output_directory_var.set(selected)

    def _refresh_export_button(self) -> None:
        if not hasattr(self, "export_button"):
            return
        ready = (
            self._mode == "ready"
            and self._summary is not None
            and any(
                variable.get()
                for variable, _ in self._slice_rows.values()
            )
        )
        self.export_button.configure(
            state="normal" if ready else "disabled"
        )

    def _set_mode(self, mode: UiMode | str) -> None:
        self._mode = UiMode(mode)
        busy = self._mode.is_busy
        cancelling = self._mode == UiMode.CANCELLING
        if hasattr(self, "choose_file_button"):
            self.choose_file_button.configure(
                state="disabled" if busy else "normal"
            )
        if hasattr(self, "cancel_button"):
            self.cancel_button.configure(
                state=(
                    "disabled"
                    if (
                        not self._mode.can_cancel
                        or cancelling
                        or self._mode == UiMode.SHUTTING_DOWN
                    )
                    else "normal"
                )
            )
        if hasattr(self, "open_output_button"):
            has_output = (
                self._last_result is not None
                and self._last_result.output_directory.exists()
            )
            self.open_output_button.configure(
                state="normal" if has_output and not busy else "disabled"
            )
        if hasattr(self, "open_report_button"):
            has_report = (
                self._last_result is not None
                and self._last_result.validation_text_path is not None
                and self._last_result.validation_text_path.exists()
            )
            self.open_report_button.configure(
                state="normal" if has_report and not busy else "disabled"
            )
        self._refresh_export_button()

    def _settings_from_form(self, *, strict: bool = False) -> AppSettings:
        try:
            target_width = int(self.target_width_var.get().strip())
        except ValueError as error:
            if strict:
                raise FormValidationError(
                    "目标宽度必须是正整数。"
                ) from error
            target_width = self._settings.target_width
        try:
            jpeg_quality = int(self.jpeg_quality_var.get().strip())
        except ValueError as error:
            if strict:
                raise FormValidationError(
                    "JPEG 质量必须是 1 到 100 的整数。"
                ) from error
            jpeg_quality = self._settings.jpeg_quality
        background = self.jpeg_background_var.get().strip().upper()
        try:
            parse_hex_color(background)
        except ValueError:
            if strict:
                raise FormValidationError(
                    "JPEG 背景色必须是 #RRGGBB 格式。"
                )
            background = self._settings.jpeg_background
        output_text = self.output_directory_var.get().strip()
        try:
            return AppSettings(
                output_directory=Path(output_text) if output_text else None,
                width_mode=(
                    "original"
                    if self.width_mode_var.get() == "原始宽度"
                    else "custom"
                ),
                target_width=target_width if strict else max(1, target_width),
                allow_upscale=self.allow_upscale_var.get(),
                output_format=_LABEL_TO_FORMAT[self.format_var.get()],
                jpeg_quality=(
                    jpeg_quality
                    if strict
                    else min(100, max(1, jpeg_quality))
                ),
                jpeg_background=background,
                color_policy=_LABEL_TO_COLOR[self.color_policy_var.get()],
                create_zip=self.create_zip_var.get(),
                open_output_folder=self.open_output_var.get(),
                naming_rule=_LABEL_TO_NAMING[self.naming_rule_var.get()],
                photoshop_fallback=_LABEL_TO_PHOTOSHOP[
                    self.photoshop_fallback_var.get()
                ],
            )
        except (TypeError, ValueError) as error:
            if strict:
                raise FormValidationError(str(error)) from error
            raise

    def _save_settings_safely(self) -> None:
        try:
            settings = self._settings_from_form()
            self._settings_store.save(settings)
            self._settings = settings
        except Exception as error:
            self.status_var.set(f"设置未能保存：{error}")

    def _open_last_output(self) -> None:
        if self._last_result is None:
            return
        try:
            open_in_file_manager(self._last_result.output_directory)
        except OSError as error:
            messagebox.showerror("无法打开目录", str(error), parent=self)

    def _open_last_report(self) -> None:
        if (
            self._last_result is None
            or self._last_result.validation_text_path is None
        ):
            return
        try:
            open_file(self._last_result.validation_text_path)
        except OSError as error:
            messagebox.showerror("无法打开报告", str(error), parent=self)

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._save_settings_safely()
        self._set_mode("shutting_down")
        self.status_var.set("正在安全关闭并释放文档缓存…")
        if self._poll_after_id is not None:
            self.after_cancel(self._poll_after_id)
            self._poll_after_id = None
        if self._runner.close():
            self._destroy_after_shutdown()
        else:
            self.after(100, self._poll_shutdown)

    def _poll_shutdown(self) -> None:
        self._drain_events_during_shutdown()
        if not self._runner.worker_alive:
            self._destroy_after_shutdown()
            return
        self.after(100, self._poll_shutdown)

    def _drain_events_during_shutdown(self) -> None:
        for _ in range(self._MAX_EVENTS_PER_POLL):
            try:
                event = self._runner.events.get_nowait()
            except queue.Empty:
                break
            if isinstance(event, Failed):
                self.status_var.set(
                    f"关闭资源时发生错误：{event.message}"
                )

    def _destroy_after_shutdown(self) -> None:
        if self._preview_pil is not None:
            self._preview_pil.close()
            self._preview_pil = None
        self.destroy()
