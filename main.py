import time
import os
import signal
import io
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from PIL import Image
import numpy as np
import cv2

http_port = 3333
selenium_port = 8080
stream_url = "https://play.ollieq.co.uk/admin/streams/1"
chrome_driver_path = "./chromedriver"

app = Flask(__name__)

def setup_stream(driver):
    driver.get(stream_url)
    time.sleep(1)  # Implicit wait
    start_button = driver.find_element(By.XPATH, "//button[text()='Start']")
    start_button.click()

def detect_spot_id(img):
    # Convert the image to grayscale
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Initialize the QRCode detector
    qr_decoder = cv2.QRCodeDetector()

    # Detect and decode the QR code
    data, points, _ = qr_decoder.detectAndDecode(img)
    
    if points is not None:
        try:
            spot_id = int(data)
            return spot_id
        except ValueError:
            return -1
    else:
        return -1

def process_image(opencv_image):
    # Increase contrast
    img = cv2.convertScaleAbs(opencv_image, alpha=1.5, beta=0)

    # fix the lens distortion given the following parameters
    K = np.array([[1.89650447e+03, 0.00000000e+00, 1.78896234e+03],
                  [0.00000000e+00, 1.89324303e+03, 1.37414153e+03],
                  [0.00000000e+00, 0.00000000e+00, 1.00000000e+00]])
    D = np.array([[-0.3995337, 0.32938276, 0.00629111, -0.00174244, -0.10516765]])  # Add your distortion coefficients here if applicable
    original_h, original_w = img.shape[:2]
    newcameramtx, roi = cv2.getOptimalNewCameraMatrix(K, D, (original_w,original_h), 1, (original_w,original_h))
    dst = cv2.undistort(img, K, D, None, newcameramtx)


    # crop the image
    x, y, w, h = roi
    img = dst[y:y+original_h, x:x+original_w]
    # stretch back to original size
    img = cv2.resize(img, (original_w, original_h))
    return img

def save_image(driver):
    _id = time.strftime('%Y-%m-%d-%H-%M-%S')
    processed_path = f"./screenshots/{_id}-processed.png"
    raw_path = f"./screenshots/{_id}-raw.png"
    time.sleep(0.5) # wait for flash to settle bitrate
    screenshot = driver.get_screenshot_as_png()
    # convert screenshot to opencv image

    buffer = io.BytesIO(screenshot)

    array = np.asarray(bytearray(buffer.read()), dtype=np.uint8)
    img = cv2.imdecode(array, cv2.IMREAD_COLOR)

    processed_image = process_image(img)
    
    with open(processed_path, 'wb') as f:
        cv2.imwrite(processed_path, processed_image)
        cv2.imwrite(raw_path, img)
    
    return processed_image

@app.route('/', methods=['GET'])
def get_root():
    processed_image = save_image(driver)
    
    spot_id = detect_spot_id(processed_image)
    if spot_id == -1:
        return "Error scanning QR code", 500
    
    return jsonify({"spot_id": spot_id})

if __name__ == '__main__':
    # loop through screenshots folder
    # for filename in os.listdir('./screenshots'):
    #     if filename.endswith('.png'):
    #         path = f"./screenshots/{filename}"
    #         img = cv2.imread(path)
    #         undistorted_image = process_image(img)
    #         cv2.imwrite(path + "new.png", undistorted_image)

    print(cv2.__version__)
    
    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    
    service = Service(chrome_driver_path)
    service.start()
    
    driver = webdriver.Remote(service.service_url, options=options)
    
    signal.signal(signal.SIGINT, lambda sig, frame: (service.stop(), driver.quit(), os._exit(0)))
    
    try:
        setup_stream(driver)
    except Exception as e:
        print(f"Error setting up stream: {e}")
        service.stop()
        driver.quit()
        os._exit(1)
    
    app.run(host="0.0.0.0", port=http_port)
