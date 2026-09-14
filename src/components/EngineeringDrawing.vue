<script setup>
// Own engineering-sheet settings and PDF requests independently of model generation.
import { onBeforeUnmount, reactive, ref, watch } from 'vue'

const props = defineProps({ stepUrl: { type: String, required: true }, name: String })
const form = reactive({
  title: (props.name || '零件工程图').replace(/\.[^.]+$/, '').slice(0, 24),
  drawingNumber: '', organization: '', material: '', notes: '', paper: 'A3',
  axis: 'auto', rotation: 0, sectionPercent: 50, sectionOffset: 0, scale: 0,
  hiddenLines: true, dimensions: true, centerlines: true,
})
const busy = ref(false)
const error = ref('')
const output = ref(null)
let controller = null

// Discard an obsolete preview when its drawing settings change.
function invalidate() {
  output.value = null
  error.value = ''
}

// Resolve the PDF URL against the same configured API endpoint as the STEP model.
function pdfUrl(path) {
  return props.stepUrl.split('/drawings/')[0] + path.replace(/^\/api/, '')
}

// Generate a new revision only from the already validated STEP result.
async function generate() {
  if (busy.value) return
  busy.value = true
  invalidate()
  controller = new AbortController()
  try {
    const response = await fetch(props.stepUrl.replace(/\/model\.step$/, '/engineering-pdf'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form), signal: controller.signal,
    })
    const result = await response.json()
    if (!response.ok) {
      throw new Error(typeof result.detail === 'string' ? result.detail : '请检查图纸设置中的数值和文字长度。')
    }
    output.value = { ...result, pdfUrl: pdfUrl(result.pdfUrl) }
  } catch (failure) {
    if (failure.name !== 'AbortError') error.value = failure.message
  } finally {
    busy.value = false
  }
}

// Cancel requests when the parent switches to another model or leaves the page.
function dispose() {
  controller?.abort()
}

watch(form, invalidate, { deep: true })
onBeforeUnmount(dispose)
</script>

<template>
  <section class="panel engineering-drawing">
    <div class="panel-heading">
      <h2>STEP → 工程图 PDF</h2>
      <span class="small-label">主视图 · 端视图 · 纵剖 · 横截面</span>
    </div>
    <p class="drawing-help">
      自动标注外形尺寸与可识别的横截面圆径。公差、粗糙度、螺纹规格及工艺要求请在说明中填写。
    </p>
    <form @submit.prevent="generate">
      <fieldset :disabled="busy">
        <div class="pdf-fields">
          <label>零件名称<input v-model="form.title" required maxlength="24" /></label>
          <label>图号<input v-model="form.drawingNumber" maxlength="32" /></label>
          <label>单位名称<input v-model="form.organization" maxlength="32" /></label>
          <label>材料<input v-model="form.material" maxlength="24" placeholder="未指定" /></label>
          <label>图幅<select v-model="form.paper"><option>A3</option><option>A4</option></select></label>
          <label>比例<select v-model.number="form.scale">
            <option :value="0">自动适配</option><option :value="1">1:1</option>
            <option :value="0.5">1:2</option><option :value="0.25">1:4</option>
            <option :value="0.2">1:5</option><option :value="0.1">1:10</option>
          </select></label>
          <label>模型长轴<select v-model="form.axis">
            <option value="auto">自动（最长方向）</option><option value="x">X 轴</option>
            <option value="y">Y 轴</option><option value="z">Z 轴</option>
          </select></label>
          <label>绕长轴旋转（°）<input v-model.number="form.rotation" type="number" min="-180" max="180" step="any" required /></label>
          <label>横截面位置（距左端 %）<input v-model.number="form.sectionPercent" type="number" min="0.01" max="99.99" step="any" required /></label>
          <label>纵剖偏移（距中心 mm）<input v-model.number="form.sectionOffset" type="number" min="-100000" max="100000" step="any" required /></label>
        </div>
        <div class="pdf-options">
          <label><input v-model="form.hiddenLines" type="checkbox" />显示隐藏线</label>
          <label title="参考线取模型包围盒中心，不代表设计基准"><input v-model="form.centerlines" type="checkbox" />显示中心参考线</label>
          <label><input v-model="form.dimensions" type="checkbox" />自动几何尺寸</label>
        </div>
        <label class="pdf-notes">技术要求 / 公差 / 表面要求
          <textarea v-model="form.notes" maxlength="800" rows="4" placeholder="填写实际设计要求；不填写时会在图纸中注明未指定。" />
        </label>
        <button class="primary" type="submit">{{ busy ? '正在计算投影与剖视图…' : '生成工程图 PDF' }}</button>
      </fieldset>
    </form>
    <div v-if="error" class="error" role="alert">{{ error }}</div>
    <div v-if="output" class="pdf-result">
      <div class="pdf-actions">
        <span>{{ output.verification.paper }} · 4 个视图 · 比例 {{ output.verification.scale >= 1 ? `${output.verification.scale}:1` : `1:${1 / output.verification.scale}` }}</span>
        <a :href="output.pdfUrl" target="_blank" rel="noopener">打开 PDF 预览</a>
        <a class="button-link" :href="`${output.pdfUrl}?download=true`" download>下载工程图 PDF</a>
      </div>
      <iframe :src="output.pdfUrl" title="工程图 PDF 预览" />
    </div>
  </section>
</template>

<style scoped>
/* Keep drawing configuration contained while reusing the workspace panel styles. */
.engineering-drawing { margin-top: 22px; }
.drawing-help { color: #607675; font-size: 13px; line-height: 1.7; }
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
.pdf-fields { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.pdf-fields label, .pdf-notes { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.pdf-fields input, .pdf-fields select, textarea { width: 100%; box-sizing: border-box; border: 1px solid #d7e2df; border-radius: 6px; padding: 9px; font: inherit; background: white; color: #234342; }
.pdf-options { display: flex; gap: 24px; flex-wrap: wrap; margin: 18px 0; font-size: 13px; }
.pdf-options label { display: flex; flex-direction: row; align-items: center; gap: 7px; margin: 0; }
.pdf-options input { width: auto; }
.pdf-notes { margin-bottom: 15px; }
.pdf-actions { display: flex; gap: 18px; flex-wrap: wrap; align-items: center; margin: 20px 0 12px; }
.pdf-actions span { margin-right: auto; font-size: 13px; }
iframe { display: block; width: 100%; height: 620px; border: 1px solid #d7e2df; border-radius: 8px; background: #eef2f1; }
@media (max-width: 800px) { .pdf-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 480px) { .pdf-fields { grid-template-columns: 1fr; } }
</style>
