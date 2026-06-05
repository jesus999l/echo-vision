from core.system_spine import classify_and_route

while True:
    user_input = input(">> ")
    result = classify_and_route(user_input)
    print("ROUTE:", result)
