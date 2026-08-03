import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  ChevronDown,
  CircleAlert,
  FileText,
  FolderOpen,
  Image as ImageIcon,
  Info,
  LoaderCircle,
  Play,
  ShieldCheck,
  Sparkles,
  Square,
  X,
} from 'lucide-react'
import { bridge, demoDocument } from './services/bridge'
import logoWhite from './assets/brand/logo-white.svg'
import symbolWhite from './assets/brand/symbol-white.svg'
import { BRAND } from './config/brand'
import type {
  ApiResponse,
  AppEvent,
  AppSettings,
  DocumentInfo,
  ExportProgress,
  ExportResult,
  SliceInfo,
  UiMode,
} from './types'

const phaseText: Record<string, string> = {
  preparing: '正在校验源文件',
  parsing: '正在读取切片信息',
  reading_composite: '正在解码 Photoshop 合成图',
  photoshop: '正在等待 Photoshop 高保真渲染',
  resizing: '正在统一缩放画布',
  starting: '正在创建安全输出目录',
  exporting: '正在导出切片',
  written: '切片已写入并验证',
  validating: '正在生成验证报告',
  archiving: '正在创建 ZIP 压缩包',
}

const compositeText: Record<string, string> = {
  embedded_merged: '内嵌高保真合成图',
  embedded_merged_unverified: '内嵌合成图（未验证）',
  photoshop: 'Photoshop 临时副本渲染',
  missing: '缺少合成图',
  invalid: '合成图不可用',
}

const initialSettings: AppSettings = {
  output_directory: '',
  width_mode: 'original',
  target_width: 1440,
  allow_upscale: true,
  output_format: 'png',
  jpeg_quality: 95,
  jpeg_background: '#FFFFFF',
  color_policy: 'auto',
  create_zip: false,
  open_output_folder: true,
  naming_rule: 'sequence_dimensions',
  photoshop_fallback: 'disabled',
}

function messageFrom<T>(response: ApiResponse<T>): string | null {
  return response.success ? null : response.error?.message ?? '操作失败。'
}

function outputSize(slice: SliceInfo, document: DocumentInfo, settings: AppSettings) {
  if (settings.width_mode === 'original') return [slice.width, slice.height]
  const effectiveWidth = !settings.allow_upscale
    ? Math.min(settings.target_width, document.width)
    : settings.target_width
  const scale = effectiveWidth / document.width
  return [Math.round(slice.width * scale), Math.round(slice.height * scale)]
}

function App() {
  const [version, setVersion] = useState('0.3.1')
  const [settings, setSettings] = useState<AppSettings>(initialSettings)
  const [document, setDocument] = useState<DocumentInfo | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [mode, setMode] = useState<UiMode>('idle')
  const [progress, setProgress] = useState<ExportProgress | null>(null)
  const [result, setResult] = useState<ExportResult | null>(null)
  const [taskId, setTaskId] = useState<number | null>(null)
  const [toast, setToast] = useState<{ tone: 'error' | 'success'; text: string } | null>(null)
  const [dragging, setDragging] = useState(false)
  const [aboutOpen, setAboutOpen] = useState(false)
  const [showSplash, setShowSplash] = useState(true)
  const initialized = useRef(false)

  useEffect(() => {
    const timeout = window.setTimeout(() => setShowSplash(false), 780)
    return () => window.clearTimeout(timeout)
  }, [])

  useEffect(() => {
    if (!aboutOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setAboutOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [aboutOpen])

  useEffect(() => {
    const cards = Array.from(
      globalThis.document.querySelectorAll<HTMLElement>('.interactive-glow'),
    )
    const cleanups = cards.map((card) => {
      const move = (event: PointerEvent) => {
        const bounds = card.getBoundingClientRect()
        card.style.setProperty('--glow-x', `${event.clientX - bounds.left}px`)
        card.style.setProperty('--glow-y', `${event.clientY - bounds.top}px`)
      }
      const enter = () => card.classList.add('is-pointer-inside')
      const leave = () => card.classList.remove('is-pointer-inside')
      card.addEventListener('pointermove', move)
      card.addEventListener('pointerenter', enter)
      card.addEventListener('pointerleave', leave)
      return () => {
        card.removeEventListener('pointermove', move)
        card.removeEventListener('pointerenter', enter)
        card.removeEventListener('pointerleave', leave)
      }
    })
    return () => cleanups.forEach((cleanup) => cleanup())
  }, [])

  const showError = useCallback((text: string) => {
    setToast({ tone: 'error', text })
    window.setTimeout(() => setToast(null), 4500)
  }, [])

  const handleEvent = useCallback((event: AppEvent) => {
    if (event.type === 'bridge_error') {
      showError(event.error?.message ?? '桌面操作失败。')
      return
    }
    if (event.task_id) setTaskId(event.task_id)
    if (event.type === 'task_started') {
      setMode(event.operation === 'export' ? 'exporting' : 'loading_document')
      return
    }
    if (event.type === 'task_progress' && event.progress) {
      setProgress(event.progress)
      return
    }
    if (event.type === 'document_loaded' && event.document) {
      setDocument(event.document)
      setSelected(new Set(event.document.slices.map((slice) => slice.index)))
      setProgress(null)
      setMode(event.follow_up_task_id ? 'exporting' : 'document_ready')
      if (event.follow_up_task_id) setTaskId(event.follow_up_task_id)
      if (event.follow_up_error) showError(event.follow_up_error)
      return
    }
    if (event.type === 'export_completed' && event.result) {
      setResult(event.result)
      setProgress(null)
      setTaskId(null)
      setMode(event.result.success ? 'export_completed' : 'export_failed')
      setToast({
        tone: event.result.success ? 'success' : 'error',
        text: event.result.success
          ? `${event.result.exported_count} 张切片已成功导出`
          : '导出完成，但验证发现问题。',
      })
      window.setTimeout(() => setToast(null), 4000)
      return
    }
    if (event.type === 'task_cancelled') {
      setResult(event.result ?? null)
      setProgress(null)
      setTaskId(null)
      setMode('export_cancelled')
      return
    }
    if (event.type === 'task_failed') {
      setProgress(null)
      setTaskId(null)
      setMode(document ? 'document_ready' : 'export_failed')
      showError(event.error?.message ?? '任务失败。')
    }
  }, [document, showError])

  useEffect(() => {
    window.__PSD_SLICE_EVENT__ = handleEvent
    return () => { delete window.__PSD_SLICE_EVENT__ }
  }, [handleEvent])

  useEffect(() => {
    const initialize = async () => {
      if (initialized.current) return
      if (window.location.protocol === 'file:' && !window.pywebview?.api) return
      initialized.current = true
      const response = await bridge.initialState()
      if (!response.success || !response.data) {
        showError(response.error?.message ?? '无法初始化应用。')
        return
      }
      setVersion(response.data.version)
      setSettings(response.data.settings)
      if (!bridge.isDesktop()) {
        setDocument(demoDocument)
        setSelected(new Set(demoDocument.slices.map((slice) => slice.index)))
        setMode('document_ready')
      }
      const backlog = await bridge.events()
      backlog.data?.forEach(handleEvent)
    }
    initialize()
    window.addEventListener('pywebviewready', initialize)
    return () => window.removeEventListener('pywebviewready', initialize)
  }, [handleEvent, showError])

  const loadPath = useCallback(async (path: string) => {
    if (!path) return
    setDocument(null)
    setResult(null)
    setProgress(null)
    setMode('loading_document')
    const response = await bridge.loadDocument(path, {
      photoshop_fallback: settings.photoshop_fallback,
      photoshop_allow_launch: false,
      allow_unverified_composite: false,
    })
    const error = messageFrom(response)
    if (error) {
      setMode('idle')
      showError(error)
    } else if (response.data) {
      setTaskId(response.data.task_id)
    }
  }, [settings.photoshop_fallback, showError])

  const chooseFile = async () => {
    if (!bridge.isDesktop()) return
    const response = await bridge.selectInput()
    const error = messageFrom(response)
    if (error) showError(error)
    else if (response.data?.path) loadPath(response.data.path)
  }

  const chooseOutput = async () => {
    const response = await bridge.selectOutput()
    const error = messageFrom(response)
    if (error) showError(error)
    else if (response.data?.path) {
      setSettings((value) => ({ ...value, output_directory: response.data!.path }))
    }
  }

  const startExport = async () => {
    if (!document || selected.size === 0) return
    setMode('exporting')
    setResult(null)
    const response = await bridge.startExport({
      settings,
      selected_slice_indices: [...selected],
      photoshop_allow_launch: false,
      allow_mode_conversion: false,
      allow_unverified_composite: false,
    })
    const error = messageFrom(response)
    if (error) {
      setMode('document_ready')
      showError(error)
    } else if (response.data) {
      setTaskId(response.data.task_id)
    }
  }

  const cancel = async () => {
    setMode('cancelling')
    const response = await bridge.cancel(taskId)
    const error = messageFrom(response)
    if (error) showError(error)
  }

  const selectedCount = selected.size
  const busy = ['loading_document', 'exporting', 'cancelling'].includes(mode)
  const progressPercent = useMemo(() => {
    if (!progress?.total) return busy ? 16 : result ? 100 : 0
    const completed = progress.phase === 'exporting' ? progress.current - 1 : progress.current
    return Math.max(0, Math.min(100, (completed / progress.total) * 100))
  }, [busy, progress, result])

  const status = useMemo(() => {
    if (progress) return phaseText[progress.phase] ?? progress.phase
    if (mode === 'loading_document') return '正在展开长卷'
    if (mode === 'cancelling') return '正在安全取消'
    if (result?.success) return `${result.exported_count} 张切片已成功导出 · 源文件保持不变`
    if (mode === 'export_cancelled') return '任务已取消'
    if (document) return `长卷已展开 · ${selectedCount} / ${document.slice_count} 张切片待导出`
    return '等待展开长卷'
  }, [document, mode, progress, result, selectedCount])

  return (
    <main className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <div className="noise" />

      <FileDropHeader
        version={version}
        path={document?.source_path ?? ''}
        busy={busy}
        dragging={dragging}
        onChoose={chooseFile}
        onDragState={setDragging}
        onDrop={(path) => { setDragging(false); loadPath(path) }}
        onAbout={() => setAboutOpen(true)}
      />

      <section className="workspace">
        <DocumentPanel
          document={document}
          settings={settings}
          selected={selected}
          mode={mode}
          onToggle={(index) => setSelected((current) => {
            const next = new Set(current)
            next.has(index) ? next.delete(index) : next.add(index)
            return next
          })}
          onSelectAll={(checked) => setSelected(new Set(
            checked && document ? document.slices.map((slice) => slice.index) : [],
          ))}
        />
        <SettingsPanel
          settings={settings}
          sourceWidth={document?.width ?? null}
          disabled={busy}
          onChange={setSettings}
          onChooseOutput={chooseOutput}
        />
      </section>

      <TaskFooter
        version={version}
        mode={mode}
        status={status}
        progress={progress}
        progressPercent={progressPercent}
        result={result}
        canExport={Boolean(document && selectedCount && !busy)}
        onCancel={cancel}
        onExport={startExport}
      />

      {toast && (
        <div className={`toast ${toast.tone}`} role="status">
          {toast.tone === 'success' ? <Check size={17} /> : <CircleAlert size={17} />}
          <span>{toast.text}</span>
          <button aria-label="关闭提示" onClick={() => setToast(null)}><X size={16} /></button>
        </div>
      )}

      {aboutOpen && (
        <AboutDialog version={version} onClose={() => setAboutOpen(false)} />
      )}

      {showSplash && (
        <div className="brand-splash" aria-hidden="true">
          <div className="brand-splash-mark"><img src={symbolWhite} alt="" /></div>
          <img className="brand-splash-logo" src={logoWhite} alt="" />
          <p>{BRAND.functionalSlogan}</p>
        </div>
      )}
    </main>
  )
}

function FileDropHeader({
  version,
  path,
  busy,
  dragging,
  onChoose,
  onDragState,
  onDrop,
  onAbout,
}: {
  version: string
  path: string
  busy: boolean
  dragging: boolean
  onChoose: () => void
  onDragState: (value: boolean) => void
  onDrop: (path: string) => void
  onAbout: () => void
}) {
  const fileName = path.split(/[\\/]/).pop() || ''
  return (
    <header
      className={`glass-card interactive-glow file-drop ${dragging ? 'is-dragging' : ''}`}
      onDragEnter={(event) => { event.preventDefault(); onDragState(true) }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) onDragState(false)
      }}
      onDrop={(event) => {
        event.preventDefault()
        const file = event.dataTransfer.files[0] as File & { path?: string }
        if (file?.path) onDrop(file.path)
        else onDragState(false)
      }}
    >
      <div className="brand-lockup">
        <img className="brand-logo" src={logoWhite} alt="WENL / 长卷" />
        <span className="brand-divider" />
        <div className="brand-product">
          <strong>高保真切片导出</strong>
          <small>PSD / PSB · v{version}</small>
        </div>
      </div>
      <div className="file-copy">
        <span className="file-context">{dragging ? '准备读取' : '当前文档'}</span>
        <h1>{dragging ? '松开以读取文件' : fileName || '尚未选择文件'}</h1>
        <p title={path}>{path || '支持 PSD、PSB'}</p>
      </div>
      <div className="file-actions">
        <div className="file-action-buttons">
          <button className="button button-about" aria-label="关于 WENL 长卷" title="关于 WENL / 长卷" onClick={onAbout}>
            <Info size={15} />关于
          </button>
          <button className="button button-primary" disabled={busy} onClick={onChoose}>
            <Sparkles size={16} />选择文件
          </button>
        </div>
      </div>
    </header>
  )
}

function DocumentPanel({
  document,
  settings,
  selected,
  mode,
  onToggle,
  onSelectAll,
}: {
  document: DocumentInfo | null
  settings: AppSettings
  selected: Set<number>
  mode: UiMode
  onToggle: (index: number) => void
  onSelectAll: (checked: boolean) => void
}) {
  const loading = mode === 'loading_document'
  return (
    <section className="glass-card interactive-glow document-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">DOCUMENT</span>
          <h2>文档与切片</h2>
        </div>
        {document && <span className="status-chip"><ShieldCheck size={14} /> 本地安全处理</span>}
      </div>

      {!document ? (
        <div className="empty-state">
          {loading ? <LoaderCircle className="spin" size={34} /> : <ImageIcon size={34} />}
          <h3>{loading ? '正在展开长卷' : '将 PSD 或 PSB 拖入这里'}</h3>
          <p>{loading ? '正在读取文档、预览和切片信息；超大 PSB 可能需要稍候。' : `${BRAND.functionalSlogan} ${BRAND.localOnly}`}</p>
        </div>
      ) : (
        <>
          <div className="document-overview">
            <div className="document-meta">
              <h3>{document.file_name}</h3>
              <p>{document.width} × {document.height}px · {document.color_mode} / {document.depth} 位 · {document.has_alpha ? '含透明度' : '不透明'}</p>
              <p className="muted">合成图来源：{compositeText[document.composite_source] ?? document.composite_source}</p>
            </div>
            <div className="preview-frame">
              {document.preview_url ? (
                <img src={document.preview_url} alt="切片预览" />
              ) : (
                <div className="preview-art" aria-label="预览占位图">
                  <div className="preview-ribbon" />
                  <div className="preview-plinth" />
                  <div className="preview-copy"><b>14+</b><span>高保真切片</span></div>
                </div>
              )}
            </div>
          </div>

          <div className="slice-heading">
            <div>
              <h3>导出切片</h3>
              <span>{selected.size} / {document.slice_count} 已选择</span>
            </div>
            <div className="compact-actions">
              <button className="button button-soft" onClick={() => onSelectAll(true)}>全选</button>
              <button className="button button-ghost" onClick={() => onSelectAll(false)}>全不选</button>
            </div>
          </div>
          <div className="slice-table-head"><span>序号 / 名称</span><span>坐标</span><span>原始尺寸 → 输出尺寸</span></div>
          <div className="slice-list">
            {document.slices.map((slice) => {
              const [width, height] = outputSize(slice, document, settings)
              const checked = selected.has(slice.index)
              return (
                <button
                  key={slice.id}
                  className={`slice-row ${checked ? 'is-selected' : ''}`}
                  onClick={() => onToggle(slice.index)}
                >
                  <span className="slice-name"><CheckBox checked={checked} /><b>{String(slice.index).padStart(2, '0')}</b>{slice.name}</span>
                  <span className="slice-coordinate">({slice.left}, {slice.top})</span>
                  <span className="slice-size">{slice.width}×{slice.height}<i>→</i>{width}×{height}</span>
                </button>
              )
            })}
          </div>
        </>
      )}
    </section>
  )
}

function SettingsPanel({
  settings,
  sourceWidth,
  disabled,
  onChange,
  onChooseOutput,
}: {
  settings: AppSettings
  sourceWidth: number | null
  disabled: boolean
  onChange: (value: AppSettings) => void
  onChooseOutput: () => void
}) {
  const update = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    onChange({ ...settings, [key]: value })
  }
  const jpeg = settings.output_format === 'jpeg'
  const displayedTargetWidth = (
    settings.width_mode === 'original' && sourceWidth
      ? sourceWidth
      : settings.target_width
  )
  return (
    <aside className="glass-card interactive-glow settings-panel">
      <div className="panel-heading compact">
        <div><span className="eyebrow">EXPORT</span><h2>导出设置</h2></div>
        <span className="settings-state">自动保存</span>
      </div>

      <fieldset disabled={disabled}>
        <label className="field-label">输出宽度</label>
        <Segmented
          options={[['original', '原始宽度'], ['custom', '指定宽度']]}
          value={settings.width_mode}
          onChange={(value) => update('width_mode', value as AppSettings['width_mode'])}
        />
        <div className="inline-field">
          <label htmlFor="target-width">目标宽度</label>
          <div className={`input-with-unit ${settings.width_mode === 'custom' ? 'is-enabled' : 'is-source-width'}`}>
            <input
              id="target-width"
              type="number"
              min={1}
              value={displayedTargetWidth}
              disabled={settings.width_mode === 'original'}
              title={settings.width_mode === 'original' ? `文档原始宽度：${displayedTargetWidth}px` : '自定义输出宽度'}
              onChange={(event) => update('target_width', Math.max(1, Number(event.target.value)))}
            /><span>px</span>
          </div>
        </div>
        <Toggle label="允许放大" hint="关闭时只允许缩小或保持原尺寸" checked={settings.allow_upscale} onChange={(value) => update('allow_upscale', value)} />

        <div className="section-divider" />
        <label className="field-label">文件格式</label>
        <Segmented
          options={[['png', 'PNG'], ['jpeg', 'JPEG']]}
          value={settings.output_format}
          onChange={(value) => update('output_format', value as AppSettings['output_format'])}
        />
        <div className={`two-fields jpeg-fields ${jpeg ? 'is-enabled' : ''}`}>
          <div><label htmlFor="quality">JPEG 质量</label><input id="quality" type="number" min={1} max={100} value={settings.jpeg_quality} disabled={!jpeg} onChange={(event) => update('jpeg_quality', Number(event.target.value))} /></div>
          <div><label htmlFor="background">背景</label><div className="color-field"><span style={{ background: settings.jpeg_background }} /><input id="background" value={settings.jpeg_background} disabled={!jpeg} onChange={(event) => update('jpeg_background', event.target.value.toUpperCase())} /></div></div>
        </div>
        <SelectField label="色彩策略" value={settings.color_policy} onChange={(value) => update('color_policy', value as AppSettings['color_policy'])} options={[['auto', '自动'], ['preserve', '保留文档色彩'], ['srgb', '转换为 sRGB']]} />
        <SelectField label="文件命名" value={settings.naming_rule} onChange={(value) => update('naming_rule', value as AppSettings['naming_rule'])} options={[['sequence_dimensions', '序号 + 尺寸'], ['slice_name', '切片名 + 尺寸'], ['slice_name_with_index', '序号 + 切片名 + 尺寸']]} />

        <div className="section-divider" />
        <label className="field-label">Photoshop 高保真回退</label>
        <SelectField value={settings.photoshop_fallback} onChange={(value) => update('photoshop_fallback', value as AppSettings['photoshop_fallback'])} options={[['disabled', '禁用'], ['if_needed', '合成图不可用时'], ['always', '总是使用 Photoshop']]} />
        <p className="warning-copy">使用前请保存并关闭 Photoshop 中所有打开的文档。</p>

        <label className="field-label output-label">输出目录</label>
        <div className="output-field">
          <input value={settings.output_directory} placeholder="默认保存到源文件所在目录" onChange={(event) => update('output_directory', event.target.value)} />
          <button className="button button-soft" type="button" onClick={onChooseOutput}>浏览</button>
        </div>
        <div className="option-row">
          <Toggle label="完成后打开目录" checked={settings.open_output_folder} onChange={(value) => update('open_output_folder', value)} />
          <Toggle label="同时创建 ZIP" checked={settings.create_zip} onChange={(value) => update('create_zip', value)} />
        </div>
      </fieldset>
    </aside>
  )
}

function TaskFooter({
  version,
  mode,
  status,
  progress,
  progressPercent,
  result,
  canExport,
  onCancel,
  onExport,
}: {
  version: string
  mode: UiMode
  status: string
  progress: ExportProgress | null
  progressPercent: number
  result: ExportResult | null
  canExport: boolean
  onCancel: () => void
  onExport: () => void
}) {
  const busy = ['loading_document', 'exporting', 'cancelling'].includes(mode)
  return (
    <footer className="glass-card interactive-glow task-footer">
      <div className="task-status">
        <div className="task-title"><span className={`status-dot ${busy ? 'pulse' : ''}`} />{status}</div>
        <p>{progress?.slice ? `切片 ${progress.current}/${progress.total} · ${progress.slice.name}` : result ? `${result.output_directory} · ${result.elapsed_seconds.toFixed(1)} 秒` : `${BRAND.name} · v${version} · 本地处理 · 原文件只读`}</p>
        <div className={`progress-track ${busy && !progress?.total ? 'indeterminate' : ''}`}><i style={{ width: `${progressPercent}%` }} /></div>
      </div>
      <div className="footer-actions">
        <button className="button button-secondary" disabled={!result?.output_directory || busy} onClick={() => bridge.openOutput(result?.output_directory)}><FolderOpen size={17} />打开输出</button>
        <button className="button button-secondary" disabled={!result?.validation_text_path || busy} onClick={() => bridge.openReport(result?.validation_text_path ?? undefined)}><FileText size={17} />查看报告</button>
        {busy ? (
          <button className="button button-danger" disabled={mode === 'cancelling'} onClick={onCancel}><X size={17} />{mode === 'cancelling' ? '取消中' : '取消'}</button>
        ) : (
          <button className="button button-primary export-button" disabled={!canExport} onClick={onExport}><Play size={17} fill="currentColor" />开始导出</button>
        )}
      </div>
    </footer>
  )
}

function AboutDialog({ version, onClose }: { version: string; onClose: () => void }) {
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <section className="about-dialog" role="dialog" aria-modal="true" aria-labelledby="about-title">
        <button className="dialog-close" aria-label="关闭关于窗口" onClick={onClose}><X size={17} /></button>
        <img className="about-logo" src={logoWhite} alt="WENL / 长卷" />
        <h2 id="about-title">PSD / PSB 高保真切片导出</h2>
        <p className="about-meta"><ShieldCheck size={14} />v{version} · 本地处理</p>
      </section>
    </div>
  )
}

function Segmented({ options, value, onChange }: { options: string[][]; value: string; onChange: (value: string) => void }) {
  const selectedIndex = Math.max(0, options.findIndex(([key]) => key === value))
  return <div className="segmented"><span className={`segmented-indicator position-${selectedIndex}`} />{options.map(([key, label]) => <button type="button" key={key} className={value === key ? 'active' : ''} onClick={() => onChange(key)}>{label}</button>)}</div>
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <label className="toggle-row"><button type="button" role="switch" aria-checked={checked} className={`toggle ${checked ? 'active' : ''}`} onClick={() => onChange(!checked)}><i /></button><span>{label}{hint && <small>{hint}</small>}</span></label>
}

function SelectField({ label, value, options, onChange }: { label?: string; value: string; options: string[][]; onChange: (value: string) => void }) {
  return <label className="select-field">{label && <span>{label}</span>}<div><select value={value} onChange={(event) => onChange(event.target.value)}>{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select><ChevronDown size={16} /></div></label>
}

function CheckBox({ checked }: { checked: boolean }) {
  return <span className={`checkbox ${checked ? 'active' : ''}`}>{checked ? <Check size={14} /> : <Square size={14} />}</span>
}

export default App
