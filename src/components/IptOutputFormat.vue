<script setup>
// Present the requested IPT output separately from its actual conversion availability.
defineProps({
  modelValue: { type: String, default: 'step' },
  disabled: Boolean,
  reason: { type: String, default: '' },
})
defineEmits(['update:modelValue'])
</script>

<template>
  <div>
    <label>
      IPT 输出格式
      <select
        :value="modelValue"
        :disabled="disabled"
        aria-describedby="ipt-format-description"
        @change="$emit('update:modelValue', $event.target.value)"
      >
        <option value="step">STEP（实体几何）</option>
        <option value="sldprt">SLDPRT（原始参数化特征，尚不可用）</option>
      </select>
    </label>
    <p id="ipt-format-description" class="hint" role="status">
      {{ modelValue === 'step'
        ? '保留完整实体几何，可继续生成工程图 PDF；不包含原始草图、尺寸约束及特征历史。'
        : reason || '原始参数化特征迁移尚未实现，当前不能生成可编辑草图和特征历史的 SLDPRT。' }}
    </p>
  </div>
</template>
