import uuid

from django.db import migrations, models


def populate_resume_nonce(apps, schema_editor):
    Response = apps.get_model("surveys", "Response")
    for response in Response.objects.all():
        response.resume_nonce = uuid.uuid4()
        response.save(update_fields=["resume_nonce"])


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0002_answer_question_text_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="response",
            name="resume_nonce",
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(populate_resume_nonce, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="response",
            name="resume_nonce",
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
    ]
