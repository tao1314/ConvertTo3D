<script setup>
const props = defineProps({ drawing: Object, modelValue: Array })
const emit = defineEmits(['update:modelValue'])
function update(index, key, value) {
  emit('update:modelValue', props.modelValue.map((f,i) => i === index ? {...f, [key]: value, ...(key === 'layout' ? {profileId: ''} : {})} : f))
}
function add() {
  emit('update:modelValue', [...props.modelValue, {layout: props.drawing.layouts[0]?.name, profileId: '',
    combine: 'add', operation: 'extrude', plane: 'XY', originU: 0, originV: 0,
    positionX: 0, positionY: 0, positionZ: 0, depthMm: 10, axis: 'y', axisOffset: 0, angleDeg: 360}])
}
const fields = {originU: '视图原点 U（图纸单位）', originV: '视图原点 V（图纸单位）',
  positionX: '实体位置 X（mm）', positionY: '实体位置 Y（mm）', positionZ: '实体位置 Z（mm）'}
</script>
<template>
  <div class="part-plan">
    <strong>通用特征组合 → 一个零件</strong>
    <p class="hint">逐项选择真实截面并指定视图原点及空间位置。XY 沿 +Z 拉伸，XZ 沿 −Y，YZ 沿 +X。不同视图的原点应对应同一个零件基准。</p>
    <fieldset v-for="(f,i) in modelValue" :key="i">
      <legend>特征 {{ i+1 }}</legend>
      <label>来源布局<select :value="f.layout" @change="update(i,'layout',$event.target.value)"><option v-for="l in drawing.layouts" :key="l.name">{{ l.name }}</option></select></label>
      <label>闭合区域<select :value="f.profileId" @change="update(i,'profileId',$event.target.value)"><option value="">请选择截面</option><option v-for="p in drawing.layouts.find(l=>l.name===f.layout)?.profiles" :key="p.id" :value="p.id">{{ p.id }} · 面积 {{ p.area.toFixed(2) }} · {{ p.holes.length }} 个内环</option></select></label>
      <label>运算<select :value="f.combine" @change="update(i,'combine',$event.target.value)"><option value="add">加料</option><option v-if="i" value="cut">切除</option></select></label>
      <label>方式<select :value="f.operation" @change="update(i,'operation',$event.target.value)"><option value="extrude">拉伸</option><option value="revolve">旋转</option></select></label>
      <label>空间平面<select :value="f.plane" @change="update(i,'plane',$event.target.value)"><option>XY</option><option>XZ</option><option>YZ</option></select></label>
      <label v-for="(label,key) in fields" :key="key">{{ label }}<input type="number" step="any" :value="f[key]" @input="update(i,key,Number($event.target.value))" /></label>
      <label v-if="f.operation==='extrude'">拉伸深度（mm）<input type="number" min="0.001" step="any" :value="f.depthMm" @input="update(i,'depthMm',Number($event.target.value))" /></label>
      <template v-else>
        <label>视图内旋转轴<select :value="f.axis" @change="update(i,'axis',$event.target.value)"><option value="x">U 方向</option><option value="y">V 方向</option></select></label>
        <label>轴的垂直坐标（图纸单位）<input type="number" step="any" :value="f.axisOffset" @input="update(i,'axisOffset',Number($event.target.value))" /></label>
        <label>旋转角度（°）<input type="number" min="0.001" max="360" :value="f.angleDeg" @input="update(i,'angleDeg',Number($event.target.value))" /></label>
      </template>
      <button type="button" @click="emit('update:modelValue',modelValue.filter((_,j)=>j!==i))">移除此特征</button>
    </fieldset>
    <button type="button" :disabled="modelValue.length>=32" @click="add">添加特征</button>
  </div>
</template>
