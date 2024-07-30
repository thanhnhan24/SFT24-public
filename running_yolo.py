import cv2
from ultralytics import YOLO

# Load the YOLOv8 model
model = YOLO("F:/Code/Python/YOLO_SFT24/runs/detect/train11/weights/best.pt")

# Open the video file
video_path = 0
cap = cv2.VideoCapture(video_path)

# Loop through the video frames
while cap.isOpened():
    # Read a frame from the video
    success, frame = cap.read()

    if success:
        # Run YOLOv8 inference on the frame
        
        results = model.predict(frame)
        detected_classes = set()
        for result in results:
            for box in result.boxes:
                class_id = int(box.cls[0])
                detected_classes.add(model.names[class_id])
        
        # Print the detected classes
        if detected_classes:
            print(f"Detected classes: {', '.join(detected_classes)}")
        else:
            print("No classes detected")
        # Visualize the results on the frame
        annotated_frame = results[0].plot()

        # Display the annotated frame
        cv2.imshow("YOLOv8 Inference", annotated_frame)

        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    else:
        # Break the loop if the end of the video is reached
        break

# Release the video capture object and close the display window
cap.release()
cv2.destroyAllWindows()