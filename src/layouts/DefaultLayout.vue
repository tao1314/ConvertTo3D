<script setup>
const title = import.meta.env.VITE_APP_TITLE || 'ConvertTo3D'
</script>

<template>
  <div class="app-shell">
    <!-- <header class="app-header">
      <RouterLink to="/" class="brand">{{ title }}</RouterLink>
      <span>二维工程图重建工作台 · LOCAL WORKSPACE</span>
    </header> -->
    <main><RouterView /></main>
  </div>
</template>
