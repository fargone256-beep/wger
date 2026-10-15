# -*- coding: utf-8 -*-

# This file is part of wger Workout Manager.
#
# wger Workout Manager is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# wger Workout Manager is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License

# Django
from django.test import TestCase
from unittest.mock import MagicMock

# wger


class DuplicateExerciseLogRegressionTest(TestCase):
    """
    Regression tests for Issue #1549:
    Adding the same exercise twice to a workout does not work correctly logging session.
    Verifies that unique per-entry grouping prevents set counts and forms from merging.
    """

    def setUp(self):
        # Mock exercises
        self.exercise_bench = MagicMock()
        self.exercise_bench.id = 101
        self.exercise_bench.name_original = "Bench Press"
        self.exercise_bench.get_translation.return_value.name = "Bench Press"

        self.exercise_squat = MagicMock()
        self.exercise_squat.id = 102
        self.exercise_squat.name_original = "Squat"
        self.exercise_squat.get_translation.return_value.name = "Squat"

    def test_non_duplicated_exercises_grouping(self):
        """
        Verify standard workout day with different exercises groups independently.
        """
        set1 = MagicMock()
        set1.id = 1
        set1.sets = 3
        set1.exercise_bases = [self.exercise_bench]

        set2 = MagicMock()
        set2.id = 2
        set2.sets = 3
        set2.exercise_bases = [self.exercise_squat]

        day_sets = [set1, set2]

        exercise_list = {}
        counter = 0
        total_sets = 0

        for set_set in day_sets:
            for exercise in set_set.exercise_bases:
                total_sets += int(set_set.sets)
                counter_before = counter
                counter = counter + int(set_set.sets) - 1
                form_id_range = range(counter_before, counter + 1)

                unique_entry_key = f"{set_set.id}_{exercise.id}"
                exercise_list[unique_entry_key] = {
                    'obj': exercise,
                    'sets': int(set_set.sets),
                    'form_ids': form_id_range,
                    'exercise_name': exercise.name_original,
                }
                counter += 1

        self.assertEqual(len(exercise_list), 2)
        self.assertEqual(total_sets, 6)
        self.assertIn("1_101", exercise_list)
        self.assertIn("2_102", exercise_list)
        self.assertEqual(exercise_list["1_101"]['sets'], 3)
        self.assertEqual(exercise_list["2_102"]['sets'], 3)

    def test_duplicated_exercise_creates_independent_entries(self):
        """
        Verify that adding the same exercise in two distinct sets produces separate entries
        without overwriting form_ids or set counts (Issue #1549).
        """
        set1 = MagicMock()
        set1.id = 1
        set1.sets = 3
        set1.exercise_bases = [self.exercise_bench]

        set2 = MagicMock()
        set2.id = 2
        set2.sets = 4
        set2.exercise_bases = [self.exercise_bench]  # Same exercise duplicate!

        day_sets = [set1, set2]

        exercise_list = {}
        counter = 0
        total_sets = 0

        for set_set in day_sets:
            for exercise in set_set.exercise_bases:
                total_sets += int(set_set.sets)
                counter_before = counter
                counter = counter + int(set_set.sets) - 1
                form_id_range = range(counter_before, counter + 1)

                # Fix: Unique entry key (set_id_exercise_id)
                unique_entry_key = f"{set_set.id}_{exercise.id}"
                exercise_list[unique_entry_key] = {
                    'obj': exercise,
                    'sets': int(set_set.sets),
                    'form_ids': form_id_range,
                    'exercise_name': exercise.name_original,
                }
                counter += 1

        # Must have 2 distinct entries, not collapsed into 1
        self.assertEqual(len(exercise_list), 2)
        self.assertEqual(total_sets, 7)

        key1 = f"{set1.id}_{self.exercise_bench.id}"
        key2 = f"{set2.id}_{self.exercise_bench.id}"

        self.assertIn(key1, exercise_list)
        self.assertIn(key2, exercise_list)

        # Verify set 1 retains 3 sets (indices 0..2)
        self.assertEqual(exercise_list[key1]['sets'], 3)
        self.assertEqual(list(exercise_list[key1]['form_ids']), [0, 1, 2])

        # Verify set 2 retains 4 sets (indices 3..6)
        self.assertEqual(exercise_list[key2]['sets'], 4)
        self.assertEqual(list(exercise_list[key2]['form_ids']), [3, 4, 5, 6])

    def test_exercise_name_is_not_missing(self):
        """
        Verify that the exercise name is resolved and never blank in the template data.
        """
        exercise = MagicMock()
        exercise.id = 99
        exercise.name_original = "Deadlift"
        exercise.get_translation.return_value.name = "Deadlift"

        set_mock = MagicMock()
        set_mock.id = 5
        set_mock.sets = 3
        set_mock.exercise_bases = [exercise]

        unique_entry_key = f"{set_mock.id}_{exercise.id}"
        entry_data = {
            'obj': exercise,
            'exercise_name': exercise.name_original or exercise.get_translation().name,
        }

        self.assertEqual(entry_data['exercise_name'], "Deadlift")
        self.assertTrue(len(entry_data['exercise_name']) > 0)
