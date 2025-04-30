import ast
import operator
import re
import os
from flask import Flask, request, jsonify, Response
import requests
import xml.etree.ElementTree as ET
import yfinance as yf
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
from sympy.core.sympify import SympifyError

app = Flask(__name__)

def create_xml_response(value):
    root = ET.Element("result")
    root.text = str(value)
    xml_str = ET.tostring(root, encoding='utf-8')
    return Response(xml_str, content_type='application/xml')

@app.route("/", methods=["GET"])
def handle_query():
    query_airport = request.args.get("queryAirportTemp")
    query_stock = request.args.get("queryStockPrice")
    query_eval = request.args.get("queryEval")

    accept_header = request.headers.get("Accept", "")
    return_json = "application/json" in accept_header

    params = [query_airport, query_stock, query_eval]
    if sum(p is not None for p in params) != 1:
        return Response("Error: Provide exactly one of the three query parameters.", status=400)

    try:
        if query_airport:
            result = get_airport_temperature(query_airport)
        elif query_stock:
            result = get_stock_price(query_stock)
        elif query_eval:
            result = evaluate_expression(query_eval)
        else:
            return Response("Invalid query", status=400)

        if return_json:
            return jsonify(result)
        else:
            return create_xml_response(result)

    except Exception as e:
        return Response(f"Error: {str(e)}", status=500)

def get_airport_temperature(iata_code):
    airport_resp = requests.get(f"http://www.airport-data.com/api/ap_info.json?iata={iata_code}")
    if airport_resp.status_code != 200:
        raise Exception("Could not fetch airport data")
    airport_data = airport_resp.json()
    lat, lon = airport_data["latitude"], airport_data["longitude"]

    weather_resp = requests.get(
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    )
    if weather_resp.status_code != 200:
        raise Exception("Could not fetch weather data")
    temp = weather_resp.json()["current_weather"]["temperature"]
    return temp

def get_stock_price(symbol):
    stock = yf.Ticker(symbol)
    price = stock.history(period="1d").tail(1)["Close"].values
    if len(price) == 0:
        raise Exception("Could not retrieve stock price")
    return round(float(price[0]), 2)


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

def evaluate_expression(expr: str) -> float:
    if not re.fullmatch(r"[0-9+\-*/().\s]+", expr):
        raise Exception("Invalid characters in expression")
    
    try:
        node = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        raise Exception(f"Syntax error in expression: {e}")

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _OPERATORS:
                raise Exception(f"Unsupported operator: {op_type.__name__}")
            left = _eval(node.left)
            right = _eval(node.right)
            return _OPERATORS[op_type](left, right)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            val = _eval(node.operand)
            return +val if isinstance(node.op, ast.UAdd) else -val
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
        if isinstance(node, ast.Num):
            return node.n
        raise Exception(f"Invalid expression element: {type(node).__name__}")

    result = _eval(node)
    return float(result)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
