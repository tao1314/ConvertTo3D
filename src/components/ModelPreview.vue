<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
const props = defineProps({ url: { type: String, default: '' } })
const canvas = ref(null), error = ref('')
let triangles = [], yaw = -0.65, pitch = 0.55, zoom = 1, dragging = null, observer, requestId = 0
function parseStl(buffer) {
  const view = new DataView(buffer), count = buffer.byteLength >= 84 ? view.getUint32(80, true) : 0, result = []
  if (84 + count * 50 === buffer.byteLength) {
    for (let i = 0; i < count; i++) {
      const vertices = []
      for (let j = 0; j < 3; j++) vertices.push([0,1,2].map(k => view.getFloat32(84+i*50+12+j*12+k*4, true)))
      result.push(vertices)
    }
  } else {
    const numbers = [...new TextDecoder().decode(buffer).matchAll(/vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)/g)].map(m=>m.slice(1).map(Number))
    for (let i=0;i+2<numbers.length;i+=3) result.push(numbers.slice(i,i+3))
  }
  if (!result.length || result.some(t=>t.some(p=>p.some(v=>!Number.isFinite(v))))) throw new Error('预览网格无效')
  const min=[Infinity,Infinity,Infinity], max=[-Infinity,-Infinity,-Infinity]
  for (const t of result) for (const p of t) p.forEach((v,i)=>{min[i]=Math.min(min[i],v);max[i]=Math.max(max[i],v)})
  const center=min.map((v,i)=>(v+max[i])/2), extent=Math.max(...max.map((v,i)=>v-min[i]))||1
  return result.map(t=>t.map(p=>p.map((v,i)=>(v-center[i])/extent)))
}
function render() {
  if (!canvas.value) return
  const el=canvas.value, rect=el.getBoundingClientRect(), ratio=window.devicePixelRatio||1
  el.width=rect.width*ratio;el.height=rect.height*ratio
  const ctx=el.getContext('2d'), w=rect.width,h=rect.height,scale=Math.min(w,h)*0.65*zoom
  ctx.scale(ratio,ratio);ctx.clearRect(0,0,w,h)
  function rotate([x,y,z]) {const xx=x*Math.cos(yaw)+z*Math.sin(yaw),zz=-x*Math.sin(yaw)+z*Math.cos(yaw);return [xx,y*Math.cos(pitch)-zz*Math.sin(pitch),y*Math.sin(pitch)+zz*Math.cos(pitch)]}
  const projected=triangles.map(t=>t.map(rotate)).sort((a,b)=>a.reduce((s,p)=>s+p[2],0)-b.reduce((s,p)=>s+p[2],0))
  for (const t of projected) {
    const a=t[1].map((v,i)=>v-t[0][i]),b=t[2].map((v,i)=>v-t[0][i]),n=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    const light=Math.abs((-0.3*n[0]+0.5*n[1]+0.8*n[2])/(Math.hypot(...n)||1))
    ctx.fillStyle=`hsl(192 36% ${38+light*38}%)`;ctx.beginPath();t.forEach((p,i)=>ctx[i?'lineTo':'moveTo'](w/2+p[0]*scale,h/2-p[1]*scale));ctx.closePath();ctx.fill()
  }
  ctx.font='12px sans-serif';ctx.fillStyle='#71808a';ctx.fillText('拖动旋转 · 滚轮缩放',20,h-20)
}
async function load() {
  const id=++requestId;triangles=[];error.value='';render()
  if (!props.url) return
  try {const response=await fetch(props.url);if(!response.ok)throw new Error('模型预览加载失败');const data=await response.arrayBuffer();if(id!==requestId)return;triangles=parseStl(data);zoom=1;render()}
  catch(e){if(id===requestId)error.value=e.message}
}
function move(e){if(!dragging)return;yaw+=(e.clientX-dragging[0])*0.01;pitch+=(e.clientY-dragging[1])*0.01;dragging=[e.clientX,e.clientY];render()}
onMounted(()=>{observer=new ResizeObserver(render);observer.observe(canvas.value);load()})
watch(()=>props.url,load)
onBeforeUnmount(()=>{requestId++;observer?.disconnect()})
</script>
<template>
  <div class="model-preview">
    <canvas ref="canvas" aria-label="三维实体预览" @pointerdown="e=>{dragging=[e.clientX,e.clientY];e.target.setPointerCapture(e.pointerId)}" @pointermove="move" @pointerup="dragging=null" @pointercancel="dragging=null" @wheel.prevent="e=>{zoom=Math.max(0.2,Math.min(5,zoom*Math.exp(-e.deltaY*0.001)));render()}" />
    <p v-if="error" class="preview-empty">{{ error }}</p><p v-else-if="!url" class="preview-empty">确认轮廓与参数后，生成三维实体</p>
  </div>
</template>
