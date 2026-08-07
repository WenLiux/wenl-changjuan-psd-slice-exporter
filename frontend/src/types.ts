export type UiMode =
  | 'idle'
  | 'loading_document'
  | 'document_ready'
  | 'exporting'
  | 'cancelling'
  | 'export_completed'
  | 'export_failed'
  | 'export_cancelled'

export interface AppSettings {
  output_directory: string
  export_mode: 'slices' | 'full_canvas'
  width_mode: 'original' | 'custom'
  target_width: number
  allow_upscale: boolean
  output_format: 'png' | 'jpeg'
  jpeg_quality: number
  jpeg_background: string
  color_policy: 'auto' | 'preserve' | 'srgb'
  create_zip: boolean
  open_output_folder: boolean
  naming_rule: 'sequence_dimensions' | 'slice_name' | 'slice_name_with_index'
  photoshop_fallback: 'disabled' | 'if_needed' | 'always'
}

export interface SliceInfo {
  id: string
  index: number
  slice_id: number | null
  name: string
  left: number
  top: number
  right: number
  bottom: number
  width: number
  height: number
  is_automatic: boolean
}

export interface DocumentInfo {
  source_path: string
  file_name: string
  source_size: number
  width: number
  height: number
  color_mode: string
  depth: number
  has_alpha: boolean
  source_version: string
  slice_count: number
  excluded_slice_count: number
  slices: SliceInfo[]
  issues: Array<{ code: string; message: string; severity: string }>
  composite_source: string
  composite_is_available: boolean
  composite_is_reliable: boolean
  composite_warning: string | null
  composite_error: string | null
  preparation_mode: string
  preview_url: string | null
  preview_slice_index: number | null
}

export interface ExportProgress {
  phase: string
  current: number
  total: number
  slice: SliceInfo | null
  output_path: string | null
}

export interface ExportResult {
  status: string
  success: boolean
  export_mode: 'slices' | 'full_canvas'
  output_directory: string
  output_path: string | null
  exported_count: number
  failure_count: number
  failures: string[]
  elapsed_seconds: number
  output_format: string
  target_width: number
  validation_passed: boolean
  validation_text_path: string | null
}

export interface AppEvent {
  type: string
  task_id: number
  operation: string
  progress?: ExportProgress
  document?: DocumentInfo
  result?: ExportResult | null
  message?: string
  error?: { code: string; message: string; details: string }
  follow_up_task_id?: number
  follow_up_error?: string
}

export interface ApiResponse<T> {
  success: boolean
  data: T | null
  error: { code: string; message: string; details: string } | null
}

declare global {
  interface Window {
    pywebview?: { api: Record<string, (...args: unknown[]) => Promise<unknown>> }
    __PSD_SLICE_EVENT__?: (event: AppEvent) => void
  }
}
