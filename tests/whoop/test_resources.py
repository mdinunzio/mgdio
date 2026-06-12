"""Unit tests for the Whoop resource modules (recovery/sleep/workouts/cycles/user)."""

from __future__ import annotations

from mgdio.whoop import cycles as cycles_mod
from mgdio.whoop import recovery as recovery_mod
from mgdio.whoop import sleep as sleep_mod
from mgdio.whoop import user as user_mod
from mgdio.whoop import workouts as workouts_mod


class TestRecovery:
    def test_maps_payload(self, mock_whoop_paginate):
        mock_whoop_paginate.return_value = [
            {
                "cycle_id": 93845,
                "sleep_id": "sleep-1",
                "user_id": 10129,
                "created_at": "2026-05-12T07:30:00.000Z",
                "updated_at": "2026-05-12T07:31:00.000Z",
                "score_state": "SCORED",
                "score": {
                    "user_calibrating": False,
                    "recovery_score": 67,
                    "resting_heart_rate": 52,
                    "hrv_rmssd_milli": 48.5,
                    "spo2_percentage": 96.0,
                    "skin_temp_celsius": 33.2,
                },
            }
        ]
        result = recovery_mod.fetch_recoveries(max_records=5)
        assert len(result) == 1
        r = result[0]
        assert r.recovery_score == 67
        assert r.hrv_rmssd_milli == 48.5
        assert r.resting_heart_rate == 52
        assert r.created_at.year == 2026
        assert r.created_at.tzinfo is not None
        assert r.user_calibrating is False
        # path + max_records flow through
        assert mock_whoop_paginate.call_args.args[0] == "/v2/recovery"
        assert mock_whoop_paginate.call_args.kwargs["max_records"] == 5

    def test_unscored_record_has_none_fields(self, mock_whoop_paginate):
        mock_whoop_paginate.return_value = [
            {"sleep_id": "s", "score_state": "PENDING_SCORE"}
        ]
        r = recovery_mod.fetch_recoveries()[0]
        assert r.recovery_score is None
        assert r.hrv_rmssd_milli is None
        assert r.score_state == "PENDING_SCORE"

    def test_empty_returns_empty(self, mock_whoop_paginate):
        mock_whoop_paginate.return_value = []
        assert recovery_mod.fetch_recoveries() == []

    def test_start_end_serialized_to_params(self, mock_whoop_paginate):
        from datetime import datetime, timezone

        mock_whoop_paginate.return_value = []
        recovery_mod.fetch_recoveries(
            start=datetime(2026, 5, 1, tzinfo=timezone.utc),
            end="2026-05-12T00:00:00Z",
        )
        params = mock_whoop_paginate.call_args.kwargs["params"]
        assert params["start"] == "2026-05-01T00:00:00+00:00"
        assert params["end"] == "2026-05-12T00:00:00Z"


class TestSleep:
    def test_maps_payload(self, mock_whoop_paginate):
        mock_whoop_paginate.return_value = [
            {
                "id": "sleep-1",
                "cycle_id": 100,
                "user_id": 10129,
                "created_at": "2026-05-12T07:00:00Z",
                "updated_at": "2026-05-12T07:05:00Z",
                "start": "2026-05-11T23:30:00Z",
                "end": "2026-05-12T07:00:00Z",
                "timezone_offset": "-04:00",
                "nap": False,
                "score_state": "SCORED",
                "score": {
                    "sleep_performance_percentage": 88,
                    "sleep_efficiency_percentage": 91.2,
                    "sleep_consistency_percentage": 75,
                    "respiratory_rate": 14.6,
                    "stage_summary": {"total_rem_sleep_time_milli": 5400000},
                    "sleep_needed": {"baseline_milli": 27000000},
                },
            }
        ]
        s = sleep_mod.fetch_sleeps()[0]
        assert s.id == "sleep-1"
        assert s.sleep_performance_percentage == 88
        assert s.respiratory_rate == 14.6
        assert s.start.tzinfo is not None
        assert s.stage_summary["total_rem_sleep_time_milli"] == 5400000
        assert s.nap is False
        assert mock_whoop_paginate.call_args.args[0] == "/v2/activity/sleep"

    def test_missing_score_yields_empty_dicts(self, mock_whoop_paginate):
        mock_whoop_paginate.return_value = [{"id": "s", "score_state": "UNSCORABLE"}]
        s = sleep_mod.fetch_sleeps()[0]
        assert s.stage_summary == {}
        assert s.sleep_needed == {}
        assert s.sleep_performance_percentage is None


class TestWorkouts:
    def test_maps_payload_and_calories(self, mock_whoop_paginate):
        mock_whoop_paginate.return_value = [
            {
                "id": "w-1",
                "user_id": 10129,
                "created_at": "2026-05-12T18:00:00Z",
                "updated_at": "2026-05-12T18:30:00Z",
                "start": "2026-05-12T17:00:00Z",
                "end": "2026-05-12T18:00:00Z",
                "timezone_offset": "-04:00",
                "sport_name": "running",
                "sport_id": 0,
                "score_state": "SCORED",
                "score": {
                    "strain": 12.3,
                    "average_heart_rate": 145,
                    "max_heart_rate": 178,
                    "kilojoule": 2092.0,
                    "percent_recorded": 100.0,
                    "distance_meter": 8046.7,
                    "altitude_gain_meter": 35.0,
                    "altitude_change_meter": 2.0,
                    "zone_durations": {"zone_two_milli": 1200000},
                },
            }
        ]
        w = workouts_mod.fetch_workouts()[0]
        assert w.sport_name == "running"
        assert w.strain == 12.3
        assert w.kilojoule == 2092.0
        # 2092 kJ / 4.184 == 500 kcal
        assert abs(w.calories - 500.0) < 1e-6
        assert w.zone_durations["zone_two_milli"] == 1200000
        assert mock_whoop_paginate.call_args.args[0] == "/v2/activity/workout"

    def test_calories_none_when_kilojoule_missing(self, mock_whoop_paginate):
        mock_whoop_paginate.return_value = [{"id": "w", "score_state": "PENDING_SCORE"}]
        w = workouts_mod.fetch_workouts()[0]
        assert w.kilojoule is None
        assert w.calories is None


class TestCycles:
    def test_maps_payload(self, mock_whoop_paginate):
        mock_whoop_paginate.return_value = [
            {
                "id": 93845,
                "user_id": 10129,
                "created_at": "2026-05-12T00:00:00Z",
                "updated_at": "2026-05-12T12:00:00Z",
                "start": "2026-05-12T04:00:00Z",
                "end": None,
                "timezone_offset": "-04:00",
                "score_state": "SCORED",
                "score": {
                    "strain": 9.8,
                    "kilojoule": 8400.0,
                    "average_heart_rate": 72,
                    "max_heart_rate": 165,
                },
            }
        ]
        c = cycles_mod.fetch_cycles()[0]
        assert c.id == 93845
        assert c.strain == 9.8
        assert c.start.tzinfo is not None
        assert c.end is None  # current cycle has no end
        assert mock_whoop_paginate.call_args.args[0] == "/v2/cycle"


class TestUser:
    def test_fetch_profile(self, mock_whoop_request):
        mock_whoop_request.return_value = {
            "user_id": 10129,
            "email": "me@example.com",
            "first_name": "Mike",
            "last_name": "D",
        }
        p = user_mod.fetch_profile()
        assert p.user_id == 10129
        assert p.email == "me@example.com"
        assert p.first_name == "Mike"
        mock_whoop_request.assert_called_once_with("GET", "/v2/user/profile/basic")

    def test_fetch_body_measurement(self, mock_whoop_request):
        mock_whoop_request.return_value = {
            "height_meter": 1.83,
            "weight_kilogram": 81.6,
            "max_heart_rate": 190,
        }
        b = user_mod.fetch_body_measurement()
        assert b.height_meter == 1.83
        assert b.weight_kilogram == 81.6
        assert b.max_heart_rate == 190
        mock_whoop_request.assert_called_once_with("GET", "/v2/user/measurement/body")
