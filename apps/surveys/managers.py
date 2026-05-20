""" Managers for surveys app """

from django.db import models


class SurveyQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True)


class ResponseQuerySet(models.QuerySet):
    def complete(self):
        return self.filter(completed_at__isnull=False)

    def for_survey(self, survey):
        return self.filter(survey=survey)


class AnswerQuerySet(models.QuerySet):
    def for_question(self, question):
        return self.filter(question=question)

    def for_completed_question(self, question):
        return self.for_question(question).filter(response__completed_at__isnull=False)
