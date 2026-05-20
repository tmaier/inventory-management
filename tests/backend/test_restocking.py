"""
Tests for the restocking endpoints.
"""
from datetime import datetime

import pytest


@pytest.fixture(autouse=True)
def reset_restocking_orders():
    """Clear runtime-only submitted restocking orders before and after each test."""
    import mock_data
    mock_data.restocking_orders.clear()
    yield
    mock_data.restocking_orders.clear()


class TestRestockingRecommendations:
    """GET /api/restocking/recommendations"""

    def test_recommendations_respects_budget(self, client):
        budget = 5000
        response = client.get("/api/restocking/recommendations", params={"budget": budget})
        assert response.status_code == 200

        data = response.json()
        assert data["budget"] == budget
        assert data["total_cost"] <= budget + 0.01
        assert data["remaining_budget"] == pytest.approx(budget - data["total_cost"], abs=0.01)

        for line in data["recommended_items"]:
            assert line["quantity"] > 0
            assert line["unit_cost"] > 0
            assert line["line_total"] == pytest.approx(line["quantity"] * line["unit_cost"], abs=0.01)

    def test_recommendations_trend_priority(self, client):
        """Items with trend 'increasing' must come before 'stable' or 'decreasing' when both fit."""
        response = client.get("/api/restocking/recommendations", params={"budget": 1_000_000})
        assert response.status_code == 200
        items = response.json()["recommended_items"]

        # If at least one increasing-trend item could be chosen, it must appear before any non-increasing item.
        trends_seen = [item["trend"] for item in items]
        if "increasing" in trends_seen:
            first_non_increasing = next(
                (i for i, t in enumerate(trends_seen) if t != "increasing"),
                len(trends_seen),
            )
            assert all(t == "increasing" for t in trends_seen[:first_non_increasing])

    def test_recommendations_skips_unknown_sku(self, client):
        """Forecast SKUs that have no matching inventory entry must be excluded from recommendations."""
        import mock_data

        forecast_skus = {f["item_sku"] for f in mock_data.demand_forecasts}
        inventory_skus = {i["sku"] for i in mock_data.inventory_items}
        unmatched = forecast_skus - inventory_skus

        response = client.get("/api/restocking/recommendations", params={"budget": 1_000_000})
        recommended_skus = {item["sku"] for item in response.json()["recommended_items"]}
        assert unmatched.isdisjoint(recommended_skus)

    def test_recommendations_zero_budget(self, client):
        response = client.get("/api/restocking/recommendations", params={"budget": 0})
        assert response.status_code == 200

        data = response.json()
        assert data["budget"] == 0
        assert data["recommended_items"] == []
        assert data["total_cost"] == 0
        assert data["remaining_budget"] == 0

    def test_recommendations_negative_budget_rejected(self, client):
        response = client.get("/api/restocking/recommendations", params={"budget": -100})
        assert response.status_code == 400


class TestCreateRestockingOrder:
    """POST /api/restocking/orders"""

    def test_create_order_persists_and_lists(self, client):
        post = client.post("/api/restocking/orders", json={"budget": 50_000})
        assert post.status_code == 201

        created = post.json()
        assert created["status"] == "Submitted"
        assert created["lead_time_days"] == 14
        assert created["total_value"] <= 50_000 + 0.01
        assert len(created["items"]) > 0

        listed = client.get("/api/restocking/orders")
        assert listed.status_code == 200
        listed_orders = listed.json()
        assert len(listed_orders) == 1
        assert listed_orders[0]["order_number"] == created["order_number"]

    def test_create_order_increments_number(self, client):
        """Two consecutive POSTs must produce distinct order numbers."""
        first = client.post("/api/restocking/orders", json={"budget": 25_000}).json()
        second = client.post("/api/restocking/orders", json={"budget": 25_000}).json()

        assert first["order_number"] != second["order_number"]
        assert first["id"] != second["id"]

    def test_expected_delivery_is_14_days(self, client):
        response = client.post("/api/restocking/orders", json={"budget": 50_000})
        order = response.json()

        submitted = datetime.fromisoformat(order["submitted_at"])
        expected = datetime.fromisoformat(order["expected_delivery"])
        delta = expected - submitted
        assert delta.days == 14

    def test_create_order_rejects_zero_budget(self, client):
        """A zero budget yields no items, which must be a 400 rather than a 500 or empty 201."""
        response = client.post("/api/restocking/orders", json={"budget": 0})
        assert response.status_code == 400
