<script setup lang="ts">
// Review aid for DishIcon; safe to delete once the icons are accepted.
import { DISH_ROLES, FOOD_GROUPS } from "~/lib/dish-icon";
</script>

<template>
  <main style="padding: 24px; font: 12px system-ui; background: #f7f4ee; color: #2a2a48">
    <h1 style="font-size: 18px">Dish icons: role (rows) x food group (columns), 28px and 48px</h1>
    <table style="border-collapse: collapse">
      <thead>
        <tr>
          <th />
          <th v-for="g in FOOD_GROUPS" :key="g" style="padding: 4px 6px">{{ g }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in DISH_ROLES" :key="r">
          <th style="text-align: right; padding-right: 8px">{{ r }}</th>
          <td v-for="g in FOOD_GROUPS" :key="g" style="text-align: center; padding: 4px 6px; border-top: 1px solid #ddd">
            <div style="display: flex; gap: 6px; align-items: center; justify-content: center">
              <HomeDishIcon :role="r" :group="g" :size="28" />
              <HomeDishIcon :role="r" :group="g" :size="48" />
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </main>
</template>
