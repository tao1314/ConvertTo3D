<script setup>
import AppCard from '@/components/AppCard.vue'
import { useCounterStore } from '@/stores/counter'

const counter = useCounterStore()
</script>

<template>
  <section class="hero">
    <p class="eyebrow">项目初始化完成</p>
    <h1>开始构建 ConvertTo3D</h1>
    <p>路由、状态管理与 JavaScript 已就绪，在此基础上添加你的业务功能。</p>
  </section>
  <AppCard title="状态管理示例">
    <p>点击按钮，验证 Pinia 与 Vue 响应式状态。</p>
    <button type="button" @click="counter.increment">点击次数：{{ counter.count }}</button>
  </AppCard>
</template>
