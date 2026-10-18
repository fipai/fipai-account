from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('content', '0001_initial')]

    operations = [
        migrations.AddField(model_name='casestudy', name='automation_steps', field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name='casestudy', name='automation_steps_en', field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name='casestudy', name='business_goal', field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name='casestudy', name='business_goal_en', field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name='casestudy', name='business_tags', field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name='casestudy', name='case_type', field=models.CharField(choices=[('verified', 'Verified customer case'), ('reference', 'Reference scenario'), ('demo', 'Demo scenario')], db_index=True, default='reference', max_length=16)),
        migrations.AddField(model_name='casestudy', name='company_size', field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name='casestudy', name='display_order', field=models.IntegerField(default=1)),
        migrations.AddField(model_name='casestudy', name='human_role', field=models.TextField(blank=True)),
        migrations.AddField(model_name='casestudy', name='human_role_en', field=models.TextField(blank=True)),
        migrations.AddField(model_name='casestudy', name='metrics', field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name='casestudy', name='testimonial', field=models.TextField(blank=True)),
        migrations.AddField(model_name='casestudy', name='testimonial_author', field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name='casestudy', name='testimonial_en', field=models.TextField(blank=True)),
        migrations.AddField(model_name='casestudy', name='workflow_after', field=models.TextField(blank=True)),
        migrations.AddField(model_name='casestudy', name='workflow_after_en', field=models.TextField(blank=True)),
        migrations.AddField(model_name='casestudy', name='workflow_before', field=models.TextField(blank=True)),
        migrations.AddField(model_name='casestudy', name='workflow_before_en', field=models.TextField(blank=True)),
    ]
