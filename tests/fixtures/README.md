# Local regression fixtures

The source PSD/PSB files are large and remain outside Git. The tests locate
them through environment variables.

| Environment variable | Fixture | Slice resource | SHA-256 |
| --- | --- | --- | --- |
| `PSD_SLICE_V8_FIXTURE` | `565656未标题-1.psd` | V8 | `29d9f690872fae2013ed4fdd7aeb0becba01245b7e15dcef0ffd0bf19121a7d0` |
| `PSD_SLICE_V6_FIXTURE` | `详情切片.psb` | V6 | `e7b23a21574a3f5f442921c39a7ad5a9dad68d8746001f4277cda82b524ae288` |

Tests skip a fixture when its environment variable is not set. A fixture is
rejected if its file name, byte size, or SHA-256 fingerprint differs from the
baseline manifest.
