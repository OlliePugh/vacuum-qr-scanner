package main

import (
	"bytes"
	"errors"
	"fmt"
	"image"
	_ "image/png"
	"io"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/makiuchi-d/gozxing"
	"github.com/makiuchi-d/gozxing/qrcode"
	"github.com/tebeka/selenium"
)

const (
	httpPort = 3333
	seleniumPort = 8080
	streamUrl = "https://play.ollieq.co.uk/admin/streams/1"
	chromeDriverPath = "./chromedriver.exe"
)

// Begin viewing the stream
func setupStream(wd selenium.WebDriver) error {
	err := wd.Get(streamUrl)
	
	if err != nil {
		return err
	}
	wd.SetImplicitWaitTimeout(time.Second * 1)
	// click button that says start
	we, err := wd.FindElement(selenium.ByXPATH, "//button[text()='Start']")

	if err != nil {
		return err
	}

	return we.Click()
}

// Take an image buffer and detect QR codes in it, returns spot ID if one exists
func detectSpotId(imageBuffer []byte ) (int, error) {
	img, _, err := image.Decode(bytes.NewReader(imageBuffer))

	if err != nil {
		return -1, err
	}

	bmp, err := gozxing.NewBinaryBitmapFromImage(img)

	if err != nil {
		return -1, err
	}

	// decode image
	qrReader := qrcode.NewQRCodeReader()
	qrResult, err := qrReader.Decode(bmp, nil)
	if err != nil {
		return -1, err
	}


	spotId, err := strconv.Atoi(qrResult.GetText())

	if err != nil {
		return -1, err
	}
	
	return spotId, nil
}

// Fetch a screenshot and save to disk
func saveImage(wd selenium.WebDriver) ([]byte, error) {
	t := time.Now()
	path :=	fmt.Sprintf("./screenshots/%s.png", t.Format("2006-01-02-15-04-05-000000"))
	image, err := wd.Screenshot()
	
	if err != nil {
		return nil, err
	}
	// save image buffer to disk using io
	if err := os.WriteFile(path, image, 0644); err != nil {
		return nil, err
	}

	return image, nil
}

// Handle root request
func getRoot(w http.ResponseWriter, _ *http.Request, wd selenium.WebDriver) {
	// get current time
	rawImage, err := saveImage(wd)

	if err != nil {
		fmt.Printf("error getting screenshot: %s\n", err)
		http.Error(w, "error getting screenshot", http.StatusInternalServerError)
		return
	}

	result, err := detectSpotId(rawImage)

	if err != nil {
		fmt.Printf("error scanning qr code: %s\n", err)
		http.Error(w, "error scanning qr code", http.StatusInternalServerError)
		return
	}

	fmt.Printf("got / request\n")
	io.WriteString(w, fmt.Sprintf("%d\n", result))
}

func main() {

	service, err := selenium.NewChromeDriverService(chromeDriverPath, seleniumPort)
	if err != nil {
		panic(err)
	}

	defer service.Stop()

	// Connect to the WebDriver instance running locally.
	caps := selenium.Capabilities{"browserName": "chrome"}
	wd, err := selenium.NewRemote(caps, fmt.Sprintf("http://localhost:%d/wd/hub", seleniumPort))
	wd.ResizeWindow("", 1920, 1200)

	if err != nil {
		panic(err)
	}

	if err := setupStream(wd); err != nil {
		fmt.Printf("error setting up stream: %s\n", err)
		os.Exit(1)
	}

	defer wd.Quit()

	http.HandleFunc("/", func (w http.ResponseWriter, r *http.Request) {
		getRoot(w, r, wd)
	})

	err = http.ListenAndServe(fmt.Sprint(":", httpPort), nil)

	if errors.Is(err, http.ErrServerClosed) {
		fmt.Printf("server closed\n")
	} else if err != nil {
		fmt.Printf("error starting server: %s\n", err)
		os.Exit(1)
	}
}