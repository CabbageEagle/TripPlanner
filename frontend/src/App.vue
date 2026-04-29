<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
:root {
  color: #0f2342;
  background: #f5fbff;
  font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  min-height: 100%;
  margin: 0;
}

body {
  background: #f5fbff;
}

button,
input,
textarea,
select {
  font-family: inherit;
}
</style>
