<script setup>
defineProps({ title: { type: String, required: true } })
</script>

<template>
  <section class="card">
    <h2>{{ title }}</h2>
    <slot />
  </section>
</template>
