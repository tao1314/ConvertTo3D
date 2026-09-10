<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import ModelPreview from '@/components/ModelPreview.vue'
import FeatureBuilder from '@/components/FeatureBuilder.vue'
const features = ref([])
const api = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const workflow = ref('profile'), partId = ref(''), threadMode = ref('nominal-through')
const drawing = ref(null),
  health = ref(null),
  file = ref(null),
  busy = ref(''),
  error = ref('')
const layoutName = ref(''),
  profileId = ref(''),
  result = ref(null),
  confirmed = ref(false)
const operation = ref('extrude'),
  depthMm = ref(10),
  mmPerUnit = ref(''),
  axis = ref('y'),
  axisOffset = ref(0),
  angleDeg = ref(360),
  activeTab = ref('drawing')
const layout = computed(() =>
  drawing.value?.layouts.find((l) => l.name === layoutName.value),
)
const profile = computed(() =>
  layout.value?.profiles.find((p) => p.id === profileId.value),
)
const parts = computed(() => (drawing.value?.partCandidates || []).filter(p => p.layout === layoutName.value))
const part = computed(() => parts.value.find(p => p.id === partId.value) || parts.value[0])
const frame = computed(() => {
  const b = layout.value?.bounds || [0, 0, 100, 100],
    m = Math.max(b[2] - b[0], b[3] - b[1], 1) * 0.06
  return `${b[0] - m} ${-b[3] - m} ${b[2] - b[0] + m * 2} ${b[3] - b[1] + m * 2}`
})
const usable = computed(
  () =>
    (workflow.value === 'features' ? features.value.length && features.value.every(f => f.profileId) : workflow.value === 'part' ? part.value : profile.value) &&
    Number(mmPerUnit.value) > 0 &&
    confirmed.value &&
    (workflow.value !== 'profile' || operation.value !== 'extrude' || depthMm.value > 0),
)
const fmt = (n) =>
  Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 3 })
const points = (coords) => coords.map((p) => p.join(',')).join(' ')
const path = (p) =>
  [p.preview.outer, ...p.preview.holes]
    .map((r) => `M${r.map((v) => v.join(',')).join(' L')} Z`)
    .join(' ')
const url = (value) => value?.replace(/^\/api/, api) || ''
async function request(endpoint, options) {
  const response = await fetch(api + endpoint, options)
  let data
  try {
    data = await response.json()
  } catch {
    throw new Error('服务响应无效，请确认 Python 后端已启动。')
  }
  if (!response.ok)
    throw new Error(
      typeof data.detail === 'string'
        ? data.detail
        : '参数无效，请检查输入值。',
    )
  return data
}
async function upload() {
  if (!file.value || busy.value) return
  busy.value = '正在解析图纸…'
  error.value = ''
  result.value = null
  drawing.value = null
  try {
    const body = new FormData()
    body.append('file', file.value)
    drawing.value = await request('/drawings', { method: 'POST', body })
    layoutName.value =
      drawing.value.layouts.find((l) => l.entities.length)?.name || ''
    mmPerUnit.value =
      { 1: 25.4, 2: 304.8, 4: 1, 5: 10, 6: 1000 }[drawing.value.insunits] || ''
    profileId.value = ''
    workflow.value = drawing.value.partCandidates?.length ? 'part' : 'features'
    partId.value = drawing.value.partCandidates?.[0]?.id || ''
    confirmed.value = false
    activeTab.value = 'drawing'
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}
async function generate() {
  if (!usable.value || busy.value) return
  busy.value = '正在构建并校验实体…'
  error.value = ''
  result.value = null
  try {
    const wholePart = workflow.value === 'part'
    const composed = workflow.value === 'features'
    result.value = await request(`/drawings/${drawing.value.id}/${composed ? 'generate-features' : wholePart ? 'generate-part' : 'generate'}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(composed ? {features: features.value, mmPerUnit: Number(mmPerUnit.value), confirmed: confirmed.value} : wholePart ? {
        partId: part.value.id, mmPerUnit: Number(mmPerUnit.value),
        threadMode: threadMode.value, edgeTreatment: 'omit', confirmed: confirmed.value,
      } : {
        layout: layoutName.value,
        profileId: profileId.value,
        operation: operation.value,
        mmPerUnit: Number(mmPerUnit.value),
        depthMm: Number(depthMm.value),
        axis: axis.value,
        axisOffset: Number(axisOffset.value),
        angleDeg: Number(angleDeg.value),
        confirmed: confirmed.value,
      }),
    })
    activeTab.value = 'model'
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}
watch(layoutName, () => {
  profileId.value = ''
  partId.value = ''
  if (workflow.value !== 'features') workflow.value = parts.value.length ? 'part' : 'features'
})
watch(features, () => { confirmed.value = false; result.value = null }, {deep: true})
watch(file, () => {
  features.value = []
  drawing.value = null
  result.value = null
  profileId.value = ''
  confirmed.value = false
})
watch(
  [
    layoutName,
    profileId,
    operation,
    depthMm,
    mmPerUnit,
    axis,
    axisOffset,
    angleDeg,
    workflow, partId, threadMode,
  ],
  () => {
    confirmed.value = false
    result.value = null
  },
)
async function refreshHealth() {
  try {
    health.value = await request('/health')
  } catch {
    health.value = { offline: true }
  }
}
onMounted(refreshHealth)
</script>
<template>
  <section class="hero">
    <div>
      <p class="eyebrow">ENGINEERING DRAWING → SOLID MODEL</p>
      <h1>从工程图，到三维实体</h1>
      <p class="subtitle">
        导入 Inventor 导出的二维 DWG / DXF，重建实体并输出 SolidWorks 可读取的 STEP。
      </p>
    </div>
    <button
      class="service-pill"
      title="点击刷新服务状态"
      @click="refreshHealth"
      :class="{ warning: !health?.dwgParser || !health?.cadKernel }"
    >
      <i />{{
        !health
          ? '连接服务中'
          : health.offline
            ? '本地服务未启动'
            : health.dwgParser && health.cadKernel
              ? '本地 CAD 服务就绪'
              : 'CAD 依赖未就绪'
      }}
    </button>
  </section>
  <div v-if="health?.offline" class="notice">
    请先运行 <code>npm run server</code> 启动本地解析服务，再刷新页面。
  </div>
  <div class="steps">
    <span :class="{ done: drawing }"><b>01</b> 导入图纸</span
    ><span :class="{ done: profile }"><b>02</b> 确认轮廓</span
    ><span :class="{ done: result }"><b>03</b> 生成实体</span>
  </div>
  <div v-if="error" class="error" role="alert">{{ error }}</div>
  <div
    v-if="
      drawing &&
      !drawing.layouts.some((l) =>
        l.annotations.some((a) => a.type === 'DIMENSION'),
      )
    "
    class="notice"
  >
    此图纸未检测到尺寸标注。轴测图中的闭合区域不等于真实截面；如需还原原零件，请补充尺寸或正投影／剖视图。
  </div>
  <div class="workbench" :aria-busy="!!busy">
    <aside class="panel controls">
      <div class="panel-heading">
        <h2>图纸与建模</h2>
        <span class="small-label">DWG / DXF</span>
      </div>
      <label class="upload-box"
        ><span class="upload-icon">↥</span
        ><strong>{{ file?.name || '选择二维工程图' }}</strong
        ><span>DWG、DXF · 最大 25 MB · 本地处理</span
        ><input
          type="file"
          accept=".dwg,.dxf"
          :disabled="!!busy"
          @change="
            (e) => {
              file = e.target.files[0] || null
              error = ''
            }
          "
      /></label>
      <button
        class="primary full"
        :disabled="
          !file ||
          !!busy ||
          !health ||
          health.offline ||
          (!health.dwgParser && file.name.toLowerCase().endsWith('.dwg'))
        "
        @click="upload"
      >
        {{ busy || '解析图纸' }}
      </button>
      <template v-if="drawing">
        <div class="file-meta">
          <span>{{ drawing.dwgVersion || drawing.dxfVersion }}</span
          ><span>{{ fmt(drawing.sizeBytes / 1024) }} KB</span>
        </div>
        <fieldset :disabled="!!busy">
          <label
            >布局 / 视图空间<select v-model="layoutName">
              <option v-for="l in drawing.layouts" :key="l.name">
                {{ l.name }}
              </option>
            </select></label
          >
          <label>重建模式<select v-model="workflow"><option v-if="parts.length" value="part">同轴台阶零件自动识别方案</option><option value="features">多视图特征组合（通用）</option><option value="profile">单个二维区域拉伸 / 旋转</option></select></label>
          <FeatureBuilder v-if="workflow === 'features'" v-model="features" :drawing="drawing" />
          <div v-if="workflow === 'part' && part" class="part-plan">
            <label v-if="parts.length > 1">零件方案<select v-model="partId"><option v-for="p in parts" :key="p.id" :value="p.id">{{ p.label }}</option></select></label>
            <strong>正视图 + 右侧视图 → 1 个实体</strong>
            <p>总长 {{ fmt(part.totalLength * Number(mmPerUnit || 1)) }} mm</p>
            <p v-for="(s,i) in part.outerStages" :key="`outer${i}`">外形 {{ i+1 }}：Ø{{ fmt(2*s.radius*Number(mmPerUnit||1)) }} × {{ fmt((s.end-s.start)*Number(mmPerUnit||1)) }} mm</p>
            <p v-for="(s,i) in part.innerStages" :key="`inner${i}`">中心孔 {{ i+1 }}：Ø{{ fmt(2*s.radius*Number(mmPerUnit||1)) }}，深 {{ fmt((s.end-s.start)*Number(mmPerUnit||1)) }} mm</p>
            <p>{{ part.holes.filter(h=>!h.thread).length }} 个安装通孔 · {{ part.holes.filter(h=>h.thread).length }} 个螺纹标注孔</p>
            <label>螺纹标注孔处理<select v-model="threadMode"><option value="nominal-through">按公称直径通孔简化（无螺纹牙型）</option><option value="omit">暂不生成，保留为待确认项</option></select></label>
            <p class="hint">本次不做 R3 圆角／倒角。</p>
            <p v-for="note in part.dimensionNotes" :key="note" class="hint">{{ note }}</p>
          </div>
          <label v-if="workflow === 'profile'"
            >闭合区域<select v-model="profileId">
              <option value="" disabled>请在图中点击或选择区域</option>
              <option v-for="p in layout?.profiles" :key="p.id" :value="p.id">
                区域 {{ Number(p.id.slice(1)) + 1 }} · 面积 {{ fmt(p.area) }} ·
                {{ p.holes.length }} 个内环
              </option>
            </select></label
          >
          <p v-if="workflow === 'profile' && !layout?.profiles.length" class="hint">
            未找到闭合区域。请在 CAD 中补齐轮廓断点，或检查其他布局。
          </p>
          <label
            >图纸单位<select v-model="mmPerUnit">
              <option value="" disabled>单位未定义，请确认</option>
              <option :value="1">毫米（mm）</option>
              <option :value="10">厘米（cm）</option>
              <option :value="1000">米（m）</option>
              <option :value="25.4">英寸（in）</option>
              <option :value="304.8">英尺（ft）</option>
            </select></label
          >
          <p class="hint">
            图纸单位码：{{ drawing.insunits }}。请核对图纸比例及标注尺寸。
          </p>
          <template v-if="workflow === 'profile'">
          <label
            >建模方式<select v-model="operation">
              <option value="extrude">拉伸闭合轮廓</option>
              <option value="revolve">旋转闭合剖面</option>
            </select></label
          >
          <label v-if="operation === 'extrude'"
            >拉伸厚度（mm）<input
              v-model.number="depthMm"
              type="number"
              min="0.001"
              max="10000"
              step="any"
          /></label>
          <template v-else
            ><div class="input-row">
              <label
                >旋转轴<select v-model="axis">
                  <option value="y">Y 方向竖轴</option>
                  <option value="x">X 方向横轴</option>
                </select></label
              ><label
                >角度（°）<input
                  v-model.number="angleDeg"
                  type="number"
                  min="0.001"
                  max="360"
                  step="any"
              /></label>
            </div>
            <label
              >轴位置（图纸单位，{{ axis === 'y' ? 'X' : 'Y' }} 坐标）<input
                v-model.number="axisOffset"
                type="number"
                step="any"
            /></label>
            <p class="hint">
              选择旋转轴一侧的剖面；轴穿过区域内部时将拒绝生成。
            </p></template
          >
          </template>
          <label class="check"
            ><input v-model="confirmed" type="checkbox" /><span
              >{{ workflow === 'features' ? '已核对各截面、视图对应关系、单位及特征位置，组合为同一个零件。' : workflow === 'part' ? '已确认两视图属于同一零件、单位及孔简化方案，本次不做 R3。' : '已核对轮廓、单位及参数；本次生成基于所选区域。' }}</span
            ></label
          >
        </fieldset>
        <button
          class="primary full"
          :disabled="!usable || !!busy || !health?.cadKernel"
          @click="generate"
        >
          {{ busy || (workflow === 'part' ? '生成完整零件 →' : '生成三维实体 →') }}
        </button>
      </template>
      <p class="hint output-note">
        当前输出：STEP 实体<br />原生 SLDPRT 需在 SolidWorks 中另存；STEP
        不含原始参数化特征树。
      </p>
    </aside>
    <section class="panel viewer-panel">
      <div class="panel-heading">
        <div class="tabs">
          <button
            :class="{ active: activeTab === 'drawing' }"
            @click="activeTab = 'drawing'"
          >
            二维图纸</button
          ><button
            :class="{ active: activeTab === 'model' }"
            @click="activeTab = 'model'"
          >
            三维模型
          </button>
        </div>
        <span class="small-label">{{ drawing?.name || '等待导入' }}</span>
      </div>
      <div v-if="activeTab === 'drawing'" class="drawing-preview">
        <svg
          v-if="layout"
          :viewBox="frame"
          aria-label="二维工程图和候选闭合区域"
        >
          <g transform="scale(1,-1)">
            <template v-if="workflow === 'profile'">
            <path
              v-for="p in layout.profiles"
              :key="p.id"
              :d="path(p)"
              class="region"
              :class="{ selected: profileId === p.id }"
              fill-rule="evenodd"
              tabindex="0"
              role="button"
              :aria-label="`选择区域 ${Number(p.id.slice(1)) + 1}`"
              @click="!busy && (profileId = p.id)"
              @keydown.enter="!busy && (profileId = p.id)"
            />
            </template>
            <template v-if="workflow === 'part' && part">
              <rect class="view-outline" :x="part.frontCenter[0]-part.frontRadius-3" :y="part.frontCenter[1]-part.frontRadius-3" :width="2*part.frontRadius+6" :height="2*part.frontRadius+6" vector-effect="non-scaling-stroke" />
              <rect class="view-outline" :x="part.sideBounds[0]-3" :y="part.sideBounds[1]-3" :width="part.sideBounds[2]-part.sideBounds[0]+6" :height="part.sideBounds[3]-part.sideBounds[1]+6" vector-effect="non-scaling-stroke" />
            </template>
            <polyline
              v-for="e in layout.entities"
              :key="e.id"
              :points="points(e.points)"
              fill="none"
              stroke="currentColor"
              stroke-width="1"
              vector-effect="non-scaling-stroke"
              :class="{ construction: e.construction }"
              pointer-events="none"
            />
            <line
              v-if="workflow === 'profile' && operation === 'revolve' && profile"
              :x1="axis === 'y' ? axisOffset : layout.bounds[0]"
              :x2="axis === 'y' ? axisOffset : layout.bounds[2]"
              :y1="axis === 'x' ? axisOffset : layout.bounds[1]"
              :y2="axis === 'x' ? axisOffset : layout.bounds[3]"
              class="axis"
              vector-effect="non-scaling-stroke"
            />
          </g>
        </svg>
        <div v-else class="empty-state">
          <div class="drawing-symbol">⌑</div>
          <h3>让图纸成为建模起点</h3>
          <p>导入 DWG 或 DXF，查看实际几何与可用轮廓</p>
        </div>
        <span v-if="layout" class="canvas-caption"
          >{{ workflow === 'part' ? '两个框选视图共同约束一个零件' : '点击浅色区域选择轮廓' }} · {{ layout.entities.length }} 个几何图元</span
        >
      </div>
      <ModelPreview v-else :url="url(result?.previewUrl)" />
      <div v-if="result" class="download-bar">
        <div>
          <strong>{{ result.mode === 'multiview-single-part' ? '完整零件已生成（按所选简化方案）' : '实体已生成' }}</strong
          ><span
            >STEP 回读通过 · {{ result.stats.solids }} 个实体 ·
            {{ fmt(result.stats.volumeMm3) }} mm³</span
          >
        </div>
        <a :href="url(result.recipeUrl)" download>建模参数</a
        ><a class="button-link" :href="url(result.stepUrl)" download
          >下载 STEP ↓</a
        >
      </div>
      <div v-else class="viewer-footer">
        <span>闭合区域识别</span><span>拉伸 / 旋转</span
        ><span>实体有效性检查</span>
      </div>
    </section>
  </div>
  <section v-if="drawing" class="inspection">
    <div class="panel">
      <div class="panel-heading">
        <h2>解析概况</h2>
        <span class="small-label">实际图纸数据</span>
      </div>
      <div class="stat-row">
        <div>
          <strong>{{ layout?.profiles.length || 0 }}</strong
          ><span>候选闭合区域</span>
        </div>
        <div>
          <strong>{{ layout?.annotations.length || 0 }}</strong
          ><span>文字 / 尺寸对象</span>
        </div>
        <div>
          <strong>{{ layout?.nonPlanarCount || 0 }}</strong
          ><span>非 XY 平面图元</span>
        </div>
      </div>
      <div class="tags">
        <span v-for="(count, type) in layout?.entityCounts" :key="type"
          >{{ type }} {{ count }}</span
        >
      </div>
      <p v-if="Object.keys(layout?.unsupported || {}).length" class="hint">
        未参与建模的对象：{{
          Object.entries(layout.unsupported)
            .map(([t, n]) => `${t} × ${n}`)
            .join('、')
        }}
      </p>
    </div>
    <div class="panel">
      <div class="panel-heading">
        <h2>尺寸与文字</h2>
        <span class="small-label">供人工核对</span>
      </div>
      <div class="annotation-list">
        <p v-for="(a, i) in layout?.annotations" :key="i">
          <span>{{ a.type }}</span
          ><strong
            >{{ a.text
            }}{{
              a.measurement != null ? `（测量值 ${fmt(a.measurement)}）` : ''
            }}</strong
          >
        </p>
        <p v-if="!layout?.annotations.length" class="hint">
          未检测到独立文字或尺寸对象。尺寸可能已被分解为线段。
        </p>
      </div>
    </div>
    <div class="notice wide">
      <strong>建模范围</strong>
      <ul>
        <li v-for="warning in drawing.warnings" :key="warning">
          {{ warning }}
        </li>
      </ul>
    </div>
  </section>
</template>
