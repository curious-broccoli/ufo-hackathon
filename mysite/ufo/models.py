from django.db import models

# should I override the save() so all properties have to have a truthy value?

class Group(models.Model):
    name = models.CharField(max_length=50, unique=True)

class Submission(models.Model):
    group = models.ForeignKey(Group, models.PROTECT)
    right_predictions = models.IntegerField()
    wrong_predictions = models.IntegerField()
    cce = models.FloatField()
    time = models.DateTimeField(auto_now_add=True)
