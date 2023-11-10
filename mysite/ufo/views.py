from django.shortcuts import render
from django.http import HttpResponse, HttpRequest


def index(request: HttpRequest):
    if request.method == "POST":
        pass
    elif request.method == "GET":
        return HttpResponse("hi")
