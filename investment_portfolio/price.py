import websocket

def on_message(ws, message):
    print('on_message')
    print(message)

def on_error(ws, error):
    print('ERRRROOROOROROR')
    print(error)

def on_close(ws):
    print("### closed ###")

def on_open(ws):
    ws.send('{"type":"subscribe","symbol":"ADMCM"}')
    ws.send('{"type":"subscribe","symbol":"paskaperse"}')

if __name__ == "__main__":
    websocket.enableTrace(True)
    ws = websocket.WebSocketApp("wss://ws.finnhub.io?token=caoug5aad3icn6rp1vkg",
                              on_message = on_message,
                              on_error = on_error,
                              on_close = on_close)
    ws.on_open = on_open
    ws.run_forever()
