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

# Standard Library
import datetime
import logging

# Django
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms.models import modelformset_factory
from django.http import (
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import (
    get_object_or_404,
    render,
)
from django.urls import reverse
from django.utils.translation import gettext_lazy
from django.views.generic import (
    DeleteView,
    UpdateView,
)

# wger
from wger.core.models import (
    RepetitionUnit,
    WeightUnit,
)
from wger.manager.forms import (
    HelperWorkoutSessionForm,
    WorkoutLogForm,
    WorkoutLogFormHelper,
)
from wger.manager.models import (
    Day,
    WorkoutLog,
    WorkoutSession,
)
from wger.utils.generic_views import (
    WgerDeleteMixin,
    WgerFormMixin,
)


logger = logging.getLogger(__name__)


# ************************
# Log functions
# ************************
class WorkoutLogUpdateView(WgerFormMixin, UpdateView, LoginRequiredMixin):
    """
    Generic view to edit an existing workout log weight entry
    """

    model = WorkoutLog
    form_class = WorkoutLogForm

    def get_success_url(self):
        return reverse('manager:workout:view', kwargs={'pk': self.object.workout_id})


class WorkoutLogDeleteView(WgerDeleteMixin, DeleteView, LoginRequiredMixin):
    """
    Delete a workout log
    """

    model = WorkoutLog
    title = gettext_lazy('Delete workout log')

    def get_success_url(self):
        return reverse('manager:workout:view', kwargs={'pk': self.object.workout_id})


def add(request, pk):
    """
    Add a new workout log for a given day.
    Fixed (Issue #1549): Uses unique per-entry grouping (set_id_exercise_id)
    instead of keying strictly by exercise.id to prevent merging set counts
    when duplicate exercises exist in the workout day.
    """
    day = get_object_or_404(Day, pk=pk)
    if day.get_owner_object().user != request.user:
        return HttpResponseForbidden()

    counter = 0
    total_sets = 0
    exercise_list = {}
    form_to_exercise_base = {}

    for set_set in day.set_set.all():
        for exercise in set_set.exercise_bases:
            total_sets += int(set_set.sets)
            counter_before = counter
            counter = counter + int(set_set.sets) - 1
            form_id_range = range(counter_before, counter + 1)

            # Unique grouping per entry to avoid key collision when the same exercise is in multiple sets
            unique_entry_key = f"{set_set.id}_{exercise.id}"
            exercise_name = getattr(exercise, 'name_original', None)
            if not exercise_name and hasattr(exercise, 'get_translation'):
                trans = exercise.get_translation()
                exercise_name = getattr(trans, 'name', None) if trans else None
            if not exercise_name:
                exercise_name = str(exercise)

            exercise_list[unique_entry_key] = {
                'obj': exercise,
                'sets': int(set_set.sets),
                'set_obj': set_set,
                'form_ids': form_id_range,
                'exercise_name': exercise_name,
            }

            counter += 1
            for form_id in form_id_range:
                form_to_exercise_base[form_id] = exercise

    WorkoutLogFormSet = modelformset_factory(
        WorkoutLog,
        form=WorkoutLogForm,
        exclude=('date', 'workout'),
        extra=total_sets,
    )

    if request.method == 'POST':
        post_copy = request.POST.copy()
        for form_id in form_to_exercise_base:
            if post_copy.get(f'form-{form_id}-weight') or post_copy.get(f'form-{form_id}-reps'):
                post_copy[f'form-{form_id}-exercise_base'] = form_to_exercise_base[form_id].id

        formset = WorkoutLogFormSet(data=post_copy)
        session_form = HelperWorkoutSessionForm(data=post_copy)

        if session_form.is_valid() and formset.is_valid():
            log_date = session_form.cleaned_data['date']

            if WorkoutSession.objects.filter(user=request.user, date=log_date).exists():
                session = WorkoutSession.objects.get(user=request.user, date=log_date)
                session_form = HelperWorkoutSessionForm(data=post_copy, instance=session)

            log_instance = session_form.save(commit=False)
            if not WorkoutSession.objects.filter(user=request.user, date=log_date).exists():
                log_instance.date = log_date
                log_instance.user = request.user
                log_instance.workout = day.training
            else:
                session = WorkoutSession.objects.get(user=request.user, date=log_date)
                log_instance.instance = session
            log_instance.save()

            log_instances = [i for i in formset.save(commit=False) if i.reps]
            for log_instance in log_instances:
                if not hasattr(log_instance, 'weight_unit'):
                    log_instance.weight_unit = WeightUnit.objects.get(pk=1)
                if not hasattr(log_instance, 'repetition_unit'):
                    log_instance.repetition_unit = RepetitionUnit.objects.get(pk=1)
                if not log_instance.weight:
                    log_instance.weight = 0

                log_instance.user = request.user
                log_instance.workout = day.training
                log_instance.date = log_date
                log_instance.save()

            return HttpResponseRedirect(reverse('manager:log:log', kwargs={'pk': day.training_id}))
    else:
        user_weight_unit = 1 if getattr(getattr(request.user, 'userprofile', None), 'use_metric', True) else 2
        formset = WorkoutLogFormSet(
            queryset=WorkoutLog.objects.none(),
            initial=[
                {'weight_unit': user_weight_unit, 'repetition_unit': 1}
                for _ in range(0, total_sets)
            ],
        )

        if WorkoutSession.objects.filter(user=request.user, date=datetime.date.today()).exists():
            session = WorkoutSession.objects.get(user=request.user, date=datetime.date.today())
            session_form = HelperWorkoutSessionForm(instance=session)
        else:
            session_form = HelperWorkoutSessionForm()

    for entry_key, entry_data in exercise_list.items():
        form_id_from = min(entry_data['form_ids'])
        form_id_to = max(entry_data['form_ids'])
        entry_data['forms'] = formset[form_id_from : form_id_to + 1]

    context = {
        'day': day,
        'exercise_list': exercise_list,
        'formset': formset,
        'helper': WorkoutLogFormHelper(),
        'session_form': session_form,
        'form': session_form,
        'form_action': request.path,
    }

    return render(request, 'log/add.html', context)
