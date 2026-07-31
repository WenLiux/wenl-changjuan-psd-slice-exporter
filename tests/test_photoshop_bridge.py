from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.core.photoshop_bridge import (
    PS_DO_NOT_SAVE_CHANGES,
    PS_LOWERCASE_EXTENSION,
    PhotoshopAutomationInfo,
    PhotoshopCompositeOptions,
    PhotoshopRenderError,
    PhotoshopSafetyError,
    PhotoshopUnavailableError,
    SourceIntegrityError,
    Win32PhotoshopAutomation,
    fingerprint_file,
    read_photoshop_composite,
)


class RecordingAutomation:
    def __init__(
        self,
        *,
        size: tuple[int, int] = (10, 20),
        mode: str = "RGBA",
        mutate_path: Path | None = None,
    ) -> None:
        self.size = size
        self.mode = mode
        self.mutate_path = mutate_path
        self.calls: list[tuple[Path, Path, PhotoshopCompositeOptions]] = []

    def render_png(
        self,
        source_copy: Path,
        output_path: Path,
        options: PhotoshopCompositeOptions,
    ) -> PhotoshopAutomationInfo:
        self.calls.append((source_copy, output_path, options))
        assert source_copy.is_file()
        if self.mutate_path is not None:
            self.mutate_path.write_bytes(b"changed")
        color: int | tuple[int, ...]
        if self.mode == "RGBA":
            color = (10, 20, 30, 128)
        else:
            color = (10, 20, 30)
        image = Image.new(self.mode, self.size, color)
        try:
            image.save(output_path, format="PNG")
        finally:
            image.close()
        return PhotoshopAutomationInfo(version="26.7.0", launched=False)


def test_bridge_uses_temp_copy_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "sample.psd"
    source.write_bytes(b"source-fixture")
    before = fingerprint_file(source)
    automation = RecordingAutomation()

    result = read_photoshop_composite(
        source,
        expected_width=10,
        expected_height=20,
        source_color_mode="RGB",
        source_depth=8,
        expected_has_alpha=True,
        options=PhotoshopCompositeOptions(temp_parent=tmp_path),
        automation=automation,
    )

    assert result.source == "photoshop"
    assert result.is_reliable
    assert result.image is not None
    assert result.image.mode == "RGBA"
    assert result.image.getpixel((0, 0)) == (10, 20, 30, 128)
    assert fingerprint_file(source) == before
    assert len(automation.calls) == 1
    copied_source, output_path, _ = automation.calls[0]
    assert copied_source != source
    assert copied_source.name == "source.psd"
    assert copied_source.parent == output_path.parent
    assert not copied_source.parent.exists()
    result.image.close()


def test_bridge_rejects_non_v1_color_depth_before_automation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sixteen-bit.psb"
    source.write_bytes(b"source-fixture")
    automation = RecordingAutomation()

    with pytest.raises(PhotoshopRenderError, match="only 8-bit RGB"):
        read_photoshop_composite(
            source,
            expected_width=10,
            expected_height=20,
            source_color_mode="RGB",
            source_depth=16,
            automation=automation,
        )
    assert automation.calls == []


def test_bridge_carries_source_icc_when_photoshop_png_omits_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "profiled.psd"
    source.write_bytes(b"source-fixture")
    source_profile = b"source-icc-profile"

    result = read_photoshop_composite(
        source,
        expected_width=10,
        expected_height=20,
        source_color_mode="RGB",
        source_depth=8,
        source_icc_profile=source_profile,
        automation=RecordingAutomation(mode="RGB"),
    )

    assert result.icc_profile == source_profile
    result.image.close()


def test_bridge_rejects_wrong_rendered_dimensions_and_cleans_temp(
    tmp_path: Path,
) -> None:
    source = tmp_path / "wrong-size.psd"
    source.write_bytes(b"source-fixture")
    automation = RecordingAutomation(size=(9, 20), mode="RGB")

    with pytest.raises(PhotoshopRenderError, match="dimensions"):
        read_photoshop_composite(
            source,
            expected_width=10,
            expected_height=20,
            source_color_mode="RGB",
            source_depth=8,
            options=PhotoshopCompositeOptions(temp_parent=tmp_path),
            automation=automation,
        )

    temporary_root = automation.calls[0][0].parent
    assert not temporary_root.exists()


def test_bridge_detects_any_source_change(tmp_path: Path) -> None:
    source = tmp_path / "protected.psd"
    source.write_bytes(b"source-fixture")
    automation = RecordingAutomation(mutate_path=source)

    with pytest.raises(SourceIntegrityError, match="source PSD/PSB changed"):
        read_photoshop_composite(
            source,
            expected_width=10,
            expected_height=20,
            source_color_mode="RGB",
            source_depth=8,
            automation=automation,
        )


def test_temp_cleanup_failure_does_not_mask_render_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "cleanup.psd"
    source.write_bytes(b"source-fixture")
    automation = RecordingAutomation(size=(9, 20))
    real_rmtree = shutil.rmtree

    def fail_cleanup(path: Path) -> None:
        raise PermissionError("simulated cleanup lock")

    monkeypatch.setattr(shutil, "rmtree", fail_cleanup)
    try:
        with pytest.raises(
            PhotoshopRenderError,
            match="dimensions",
        ) as captured:
            read_photoshop_composite(
                source,
                expected_width=10,
                expected_height=20,
                source_color_mode="RGB",
                source_depth=8,
                options=PhotoshopCompositeOptions(temp_parent=tmp_path),
                automation=automation,
            )
        notes = getattr(captured.value, "__notes__", [])
        assert any("could not be deleted" in note for note in notes)
    finally:
        monkeypatch.setattr(shutil, "rmtree", real_rmtree)
        temporary_root = automation.calls[0][0].parent
        if temporary_root.exists():
            real_rmtree(temporary_root)


@dataclass
class FakePngOptions:
    Compression: int | None = None
    Interlaced: bool | None = None


class FakeDocuments:
    def __init__(self) -> None:
        self.items: list[FakeDocument] = []

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int) -> "FakeDocument":
        return self.items[index - 1]


class FakeDocument:
    _next_id = 1

    def __init__(
        self,
        app: "FakeApplication",
        name: str,
        *,
        saved: bool = True,
        fail_save: bool = False,
    ) -> None:
        self.app = app
        self.Name = name
        self.Saved = saved
        self.id = FakeDocument._next_id
        FakeDocument._next_id += 1
        self.fail_save = fail_save
        self.FullName = name
        self.close_arguments: list[int] = []
        self.save_arguments: list[tuple[Any, ...]] = []

    def SaveAs(self, *arguments: Any) -> None:
        self.save_arguments.append(arguments)
        if self.fail_save:
            raise RuntimeError("simulated save failure")
        path, _, _, _ = arguments
        image = Image.new("RGBA", (2, 2), (1, 2, 3, 4))
        try:
            image.save(path, format="PNG")
        finally:
            image.close()

    def Close(self, saving: int) -> None:
        self.close_arguments.append(saving)
        self.app.Documents.items.remove(self)


class FakeApplication:
    def __init__(
        self,
        *,
        existing: list[FakeDocument] | None = None,
        fail_save: bool = False,
    ) -> None:
        self.Documents = FakeDocuments()
        self.DisplayDialogs = 1
        self.Version = "26.7.0"
        self.fail_save = fail_save
        self.open_calls: list[str] = []
        self.owned_documents: list[FakeDocument] = []
        self.quit_calls = 0
        if existing:
            self.Documents.items.extend(existing)

    def Open(self, path: str) -> FakeDocument:
        self.open_calls.append(path)
        document = FakeDocument(
            self,
            Path(path).name,
            fail_save=self.fail_save,
        )
        document.FullName = str(Path(path).resolve())
        self.Documents.items.append(document)
        self.owned_documents.append(document)
        return document

    def Quit(self) -> None:
        self.quit_calls += 1


class FakeBindings:
    def __init__(
        self,
        app: FakeApplication,
        *,
        attach_error: Exception | None = None,
    ) -> None:
        self.app = app
        self.attach_error = attach_error
        self.png_options = FakePngOptions()
        self.initialized = 0
        self.uninitialized = 0
        self.dispatch_calls: list[str] = []

    def co_initialize(self) -> None:
        self.initialized += 1

    def co_uninitialize(self) -> None:
        self.uninitialized += 1

    def get_active_object(self, prog_id: str) -> FakeApplication:
        assert prog_id == "Photoshop.Application"
        if self.attach_error is not None:
            raise self.attach_error
        return self.app

    def dispatch(self, prog_id: str) -> Any:
        self.dispatch_calls.append(prog_id)
        if prog_id == "Photoshop.Application":
            return self.app
        assert prog_id == "Photoshop.PNGSaveOptions"
        return self.png_options


def test_com_adapter_closes_only_owned_documents_and_restores_state(
    tmp_path: Path,
) -> None:
    app = FakeApplication()
    bindings = FakeBindings(app)
    automation = Win32PhotoshopAutomation(bindings)
    source_copy = tmp_path / "source.psd"
    source_copy.write_bytes(b"fixture")
    output = tmp_path / "output.png"

    info = automation.render_png(
        source_copy,
        output,
        PhotoshopCompositeOptions(),
    )

    assert info.version == "26.7.0"
    assert not info.launched
    assert app.Documents.Count == 0
    assert app.DisplayDialogs == 1
    assert app.quit_calls == 0
    assert bindings.initialized == bindings.uninitialized == 1
    assert bindings.png_options.Compression == 6
    assert bindings.png_options.Interlaced is False
    [opened] = app.owned_documents
    assert opened.save_arguments[0][2:] == (
        True,
        PS_LOWERCASE_EXTENSION,
    )
    assert opened.close_arguments == [PS_DO_NOT_SAVE_CHANGES]


def test_com_adapter_refuses_preexisting_user_document(
    tmp_path: Path,
) -> None:
    app = FakeApplication()
    user_document = FakeDocument(
        app,
        "user-work.psd",
        saved=False,
    )
    app.Documents.items.append(user_document)
    bindings = FakeBindings(app)
    automation = Win32PhotoshopAutomation(bindings)

    with pytest.raises(
        PhotoshopSafetyError,
        match="user-work.psd \\(unsaved\\)",
    ):
        automation.render_png(
            tmp_path / "source.psd",
            tmp_path / "output.png",
            PhotoshopCompositeOptions(),
        )

    assert app.Documents.items == [user_document]
    assert app.DisplayDialogs == 1
    assert user_document.close_arguments == []
    assert app.quit_calls == 0
    assert bindings.initialized == bindings.uninitialized == 1


def test_com_adapter_cleans_up_after_render_failure(
    tmp_path: Path,
) -> None:
    app = FakeApplication(fail_save=True)
    bindings = FakeBindings(app)
    automation = Win32PhotoshopAutomation(bindings)
    source_copy = tmp_path / "source.psd"
    source_copy.write_bytes(b"fixture")

    with pytest.raises(PhotoshopRenderError, match="save failure"):
        automation.render_png(
            source_copy,
            tmp_path / "output.png",
            PhotoshopCompositeOptions(),
        )

    assert app.Documents.Count == 0
    assert app.DisplayDialogs == 1
    assert app.quit_calls == 0
    assert all(
        document.close_arguments == [PS_DO_NOT_SAVE_CHANGES]
        for document in app.owned_documents
    )


def test_com_adapter_requires_explicit_launch_permission(
    tmp_path: Path,
) -> None:
    app = FakeApplication()
    bindings = FakeBindings(
        app,
        attach_error=RuntimeError("not running"),
    )
    automation = Win32PhotoshopAutomation(bindings)

    with pytest.raises(PhotoshopUnavailableError, match="not running"):
        automation.render_png(
            tmp_path / "source.psd",
            tmp_path / "output.png",
            PhotoshopCompositeOptions(allow_launch=False),
        )
    assert "Photoshop.Application" not in bindings.dispatch_calls
    assert bindings.initialized == bindings.uninitialized == 1


def test_com_adapter_can_launch_without_ever_quitting(
    tmp_path: Path,
) -> None:
    app = FakeApplication()
    bindings = FakeBindings(
        app,
        attach_error=RuntimeError("not running"),
    )
    automation = Win32PhotoshopAutomation(bindings)
    source_copy = tmp_path / "source.psd"
    source_copy.write_bytes(b"fixture")

    info = automation.render_png(
        source_copy,
        tmp_path / "output.png",
        PhotoshopCompositeOptions(allow_launch=True),
    )

    assert info.launched
    assert bindings.dispatch_calls[0] == "Photoshop.Application"
    assert app.quit_calls == 0
    assert app.Documents.Count == 0
