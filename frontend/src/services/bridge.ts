import type { ApiResponse, AppEvent, AppSettings, DocumentInfo } from '../types'

const defaults: AppSettings = {
  output_directory: '',
  export_mode: 'slices',
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

const demoSlices = [
  [12, 0, 24543, 1440, 1917],
  [13, 0, 26460, 1440, 1677],
  [14, 0, 28137, 1440, 2027],
].map(([index, left, top, width, height]) => ({
  id: `slice-${index}`,
  index,
  slice_id: index,
  name: '未命名',
  left,
  top,
  right: left + width,
  bottom: top + height,
  width,
  height,
  is_automatic: false,
}))

export const demoDocument: DocumentInfo = {
  source_path: 'C:\\Design\\详情切片.psb',
  file_name: '详情切片.psb',
  source_size: 248_000_000,
  width: 1440,
  height: 31044,
  color_mode: 'RGB',
  depth: 8,
  has_alpha: true,
  source_version: 'PSB',
  slice_count: 14,
  excluded_slice_count: 0,
  slices: demoSlices,
  issues: [],
  composite_source: 'embedded_merged',
  composite_is_available: true,
  composite_is_reliable: true,
  composite_warning: null,
  composite_error: null,
  preparation_mode: 'disabled',
  preview_url: null,
  preview_slice_index: 12,
}

const mockResponse = <T>(data: T): ApiResponse<T> => ({
  success: true,
  data,
  error: null,
})

async function call<T>(name: string, ...args: unknown[]): Promise<ApiResponse<T>> {
  const api = window.pywebview?.api
  if (!api?.[name]) {
    if (name === 'get_initial_state') {
      return mockResponse({ version: '0.3.2', settings: defaults } as T)
    }
    if (name === 'get_events') return mockResponse([] as T)
    if (name.startsWith('open_') || name === 'save_settings') {
      return mockResponse({} as T)
    }
    return {
      success: false,
      data: null,
      error: { code: 'DESKTOP_BRIDGE_UNAVAILABLE', message: '请在桌面客户端中使用此功能。', details: '' },
    }
  }
  return (await api[name](...args)) as ApiResponse<T>
}

export const bridge = {
  initialState: () => call<{ version: string; settings: AppSettings }>('get_initial_state'),
  events: () => call<AppEvent[]>('get_events'),
  selectInput: () => call<{ path: string }>('select_input_file'),
  loadDocument: (path: string, options: Record<string, unknown>) =>
    call<{ task_id: number; path: string }>('load_document', path, options),
  selectOutput: () => call<{ path: string }>('select_output_directory'),
  saveSettings: (settings: AppSettings) => call<AppSettings>('save_settings', settings),
  startExport: (payload: Record<string, unknown>) =>
    call<{ task_id: number; reloading: boolean }>('start_export', payload),
  cancel: (taskId: number | null) => call<{ cancelled: boolean }>('cancel_export', taskId),
  openOutput: (path?: string) => call<{ path: string }>('open_output_directory', path ?? null),
  openReport: (path?: string) => call<{ path: string }>('open_report', path ?? null),
  isDesktop: () => Boolean(window.pywebview?.api),
}
