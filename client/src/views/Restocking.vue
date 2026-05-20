<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t("restocking.title") }}</h2>
      <p>{{ t("restocking.description") }}</p>
    </div>

    <!-- Budget control card -->
    <div class="card budget-card">
      <div class="card-header">
        <h3 class="card-title">{{ t("restocking.budgetLabel") }}</h3>
      </div>
      <div class="budget-body">
        <div class="budget-amount">
          {{ currencySymbol }}{{ budget.toLocaleString() }}
        </div>
        <input
          type="range"
          min="0"
          max="250000"
          step="1000"
          v-model.number="budget"
          class="budget-slider"
        />
        <div class="budget-hint">{{ t("restocking.budgetHint") }}</div>
      </div>
    </div>

    <!-- Stat cards -->
    <div class="stats-grid" v-if="!loading">
      <div class="stat-card info">
        <div class="stat-label">{{ t("restocking.budgetLabel") }}</div>
        <div class="stat-value">
          {{ currencySymbol }}{{ budget.toLocaleString() }}
        </div>
      </div>
      <div class="stat-card success">
        <div class="stat-label">{{ t("restocking.totalCost") }}</div>
        <div class="stat-value">
          {{
            recommendation
              ? currencySymbol + recommendation.total_cost.toLocaleString()
              : "—"
          }}
        </div>
      </div>
      <div :class="['stat-card', remainingVariant]">
        <div class="stat-label">{{ t("restocking.remaining") }}</div>
        <div class="stat-value">
          {{
            recommendation
              ? currencySymbol +
                recommendation.remaining_budget.toLocaleString()
              : "—"
          }}
        </div>
      </div>
    </div>

    <!-- Initial full-page load state -->
    <div v-if="loading" class="loading">{{ t("common.loading") }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Recommendations table card -->
      <div class="card" :class="{ recomputing: recomputing }">
        <div class="card-header">
          <h3 class="card-title">
            {{ t("restocking.table.name") }}
            <span v-if="recomputing" class="recomputing-indicator">...</span>
          </h3>
        </div>

        <!-- Empty state -->
        <div
          v-if="recommendation && recommendation.recommended_items.length === 0"
          class="empty-state"
        >
          {{ t("restocking.empty") }}
        </div>

        <!-- Table -->
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t("restocking.table.sku") }}</th>
                <th>{{ t("restocking.table.name") }}</th>
                <th>{{ t("restocking.table.trend") }}</th>
                <th>{{ t("restocking.table.quantity") }}</th>
                <th>{{ t("restocking.table.unitCost") }}</th>
                <th>{{ t("restocking.table.lineTotal") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in recommendation.recommended_items"
                :key="item.sku"
              >
                <td>
                  <strong>{{ item.sku }}</strong>
                </td>
                <td>{{ item.name }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{
                    t("trends." + item.trend)
                  }}</span>
                </td>
                <td>{{ item.quantity }}</td>
                <td>
                  {{ currencySymbol }}{{ item.unit_cost.toLocaleString() }}
                </td>
                <td>
                  <strong
                    >{{ currencySymbol
                    }}{{ item.line_total.toLocaleString() }}</strong
                  >
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Action row -->
        <div class="action-row">
          <div v-if="orderSuccess" class="success-banner">
            {{ t("restocking.success") }}
          </div>
          <div v-if="orderError" class="error">{{ orderError }}</div>
          <button
            class="place-order-btn"
            :disabled="
              !recommendation ||
              recommendation.recommended_items.length === 0 ||
              submitting
            "
            @click="placeOrder"
          >
            {{
              submitting
                ? t("restocking.submitting")
                : t("restocking.placeOrder")
            }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api";
import { useI18n } from "../composables/useI18n";

export default {
  name: "Restocking",
  setup() {
    const { t, currentCurrency } = useI18n();
    const router = useRouter();

    const budget = ref(50000);
    const recommendation = ref(null);
    // loading: true only on the very first fetch — blanks the whole page
    const loading = ref(true);
    // recomputing: true on subsequent slider-triggered fetches — dims table but keeps data visible
    const recomputing = ref(false);
    const error = ref(null);
    const submitting = ref(false);
    const orderSuccess = ref(false);
    const orderError = ref(null);

    const currencySymbol = computed(() => {
      return currentCurrency.value === "JPY" ? "¥" : "$";
    });

    // remaining_budget < 0 means we went over budget (shouldn't happen with greedy fill,
    // but guard anyway for display purposes)
    const remainingVariant = computed(() => {
      if (!recommendation.value) return "success";
      return recommendation.value.remaining_budget < 0 ? "warning" : "success";
    });

    const loadRecommendations = async (budgetValue, isInitial = false) => {
      if (isInitial) {
        loading.value = true;
      } else {
        recomputing.value = true;
      }
      error.value = null;

      try {
        const data = await api.getRestockingRecommendations(budgetValue);
        recommendation.value = data;
      } catch (err) {
        error.value = t("restocking.error");
        console.error("Failed to load restocking recommendations:", err);
      } finally {
        loading.value = false;
        recomputing.value = false;
      }
    };

    // Debounce slider changes: keep previous results visible while recomputing
    let debounceTimer = null;
    watch(budget, (val) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => loadRecommendations(val, false), 200);
    });

    const placeOrder = async () => {
      submitting.value = true;
      orderError.value = null;
      orderSuccess.value = false;

      try {
        await api.createRestockingOrder(budget.value);
        orderSuccess.value = true;
        // Brief pause so the user sees the success banner before navigating away
        setTimeout(() => {
          router.push("/orders");
        }, 800);
      } catch (err) {
        orderError.value =
          err.message || "Failed to place restocking order. Please try again.";
        console.error("Failed to create restocking order:", err);
      } finally {
        submitting.value = false;
      }
    };

    onMounted(() => loadRecommendations(budget.value, true));

    return {
      t,
      budget,
      recommendation,
      loading,
      recomputing,
      error,
      submitting,
      orderSuccess,
      orderError,
      currencySymbol,
      remainingVariant,
      placeOrder,
    };
  },
};
</script>

<style scoped>
/* Budget card */
.budget-card {
  margin-bottom: 1.5rem;
}

.budget-body {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.budget-amount {
  font-size: 2.5rem;
  font-weight: 700;
  color: #0f172a;
  line-height: 1;
}

.budget-slider {
  width: 100%;
  accent-color: #3b82f6;
  height: 6px;
  cursor: pointer;
}

/* Make the thumb a bit larger via webkit/moz vendor overrides */
.budget-slider::-webkit-slider-thumb {
  width: 22px;
  height: 22px;
}

.budget-slider::-moz-range-thumb {
  width: 22px;
  height: 22px;
}

.budget-hint {
  font-size: 0.813rem;
  color: #64748b;
}

/* Recomputing — dim the card content but don't remove it */
.recomputing {
  opacity: 0.6;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

.recomputing-indicator {
  font-size: 0.875rem;
  color: #64748b;
  margin-left: 0.5rem;
  font-weight: 400;
}

/* Empty state */
.empty-state {
  text-align: center;
  color: #64748b;
  padding: 2rem;
  font-size: 0.938rem;
}

/* Action row */
.action-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.5rem;
  border-top: 1px solid #e2e8f0;
  flex-wrap: wrap;
}

.place-order-btn {
  background: #3b82f6;
  color: #fff;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.938rem;
  cursor: pointer;
  transition:
    background 0.15s ease,
    opacity 0.15s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #2563eb;
}

.place-order-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Success banner */
.success-banner {
  background: #d1fae5;
  color: #065f46;
  border: 1px solid #6ee7b7;
  padding: 0.625rem 1rem;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  flex: 1;
}
</style>
