""" Add question_text_snapshot to Answer model. """

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("surveys", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="answer",
            name="question_text_snapshot",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
