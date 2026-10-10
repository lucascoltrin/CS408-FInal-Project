from django.http import HttpResponse, JsonResponse


def index(request):
    return HttpResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>SF Performance</title></head>"
        "<body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
        "<h1>Hello World</h1><p>SF Performance is running.</p>"
        "</body></html>"
    )


def health(request):
    return JsonResponse({"status": "ok"})
