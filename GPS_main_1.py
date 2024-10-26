import serial
import time
import math
import firebase_admin
import cv2
import os
from ultralytics import YOLO
from datetime import datetime
from firebase_admin import credentials, storage, firestore
from firebase_admin import db

# Hàm gửi lệnh AT tới cổng serial và nhận phản hồi
def send_at_command(port, command, timeout=2):
    try:
        # Mở kết nối serial với cổng chỉ định
        with serial.Serial(port, baudrate=15200, timeout=timeout) as ser:
            # Gửi lệnh AT đến thiết bị qua cổng COM
            ser.write((command + '\r\n').encode())
            time.sleep(0.5)  # Dừng trong 0.5 giây để đảm bảo thiết bị có thời gian phản hồi
            # Đọc toàn bộ dữ liệu phản hồi từ thiết bị
            response = ser.read_all().decode().replace('AT+CGPSINFO\r\r\n+CGPSINFO: ','')
            return response  # Trả về chuỗi phản hồi
    except serial.SerialException as e:
        return f"Error: {str(e)}"  # Xử lý lỗi nếu không thể kết nối hoặc gửi lệnh
    
# Hàm lấy thời gian từ Firebase và tính toán thời gian hiện tại và thời gian trên Firebase
def get_time():
    #thời gian hiện tại
    current_time = str(datetime.now().strftime('%H:%M')).split(':')
    #thời gian từ db
    ref = db.reference('admin/estimated_time')
    db_time = str(ref.get()).replace('"','').split(':')
    final = (int(current_time[0])-int(db_time[0]))*60+(int(current_time[1])-int(db_time[1]))
    return final
# Hàm lấy tọa độ điểm đến từ Firebase
def get_db_location():
    # Lấy dữ liệu từ nhánh "admin/destination" trong cơ sở dữ liệu
    ref_lat = db.reference('admin/destination/lat')
    ref_long = db.reference('admin/destination/long')
    data = []
    data.append(str(ref_lat.get()).replace('"',''))
    data.append(str(ref_long.get()).replace('"',''))
    return data  # Trả về danh sách chứa tọa độ điểm đến (latitude, longitude)

# Hàm xử lý chuỗi vị trí GPS, tách và thêm dấu chấm thập phân vào chuỗi tọa độ
def process_string(input_str):
    input_str = input_str.replace(".", "")  # Xóa dấu chấm trong chuỗi đầu vào
    sub_str1 = input_str[:-8]  # Phần trước 8 ký tự cuối
    sub_str2 = str(math.floor(int(input_str[-8:])*100/60))  # 8 ký tự cuối
    return f"{sub_str1}.{sub_str2}"  # Ghép lại thành chuỗi có dấu chấm thập phân

# Hàm tính khoảng cách giữa hai điểm dựa trên kinh độ và vĩ độ bằng công thức Haversine
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # Bán kính Trái đất (km)
    # Chuyển đổi độ sang radian
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    # Tính toán sự khác biệt giữa kinh độ và vĩ độ
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    # Công thức Haversine
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c  # Tính khoảng cách giữa hai điểm
    return distance  # Trả về khoảng cách tính theo km

def check_data_exists(ref_path):
    ref = db.reference(ref_path)
    data = ref.get()
    
    if data:
        #print(data)
        return data
    else:
        print("Data does not exist.")
        return False

if __name__ == '__main__':
    user_id = []
    isgoing = False
    getting_username = False
    # Load the YOLOv8 model
    model = YOLO("F://Code//Python//YOLO_SFT24//model//models//content//runs//detect//train//weights/best.pt")

    # Open the video file
    video_path = 0
    cap = cv2.VideoCapture(video_path)
    # Khai báo các biến cổng COM và lệnh AT để lấy thông tin GPS
    com_port = 'COM30'
    at_command = 'AT+CGPSINFO'
    # Đường dẫn tới tệp khóa dịch vụ Firebase
    path_to_service_account_key = 'F:/Code/Python/YOLO_SFT24/upload-video-to-android-8930c-firebase-adminsdk-ngivd-987789ede9.json'

    # Chứng thực Firebase bằng cách sử dụng tệp khóa dịch vụ
    cred = credentials.Certificate(path_to_service_account_key)
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://upload-video-to-android-8930c-default-rtdb.firebaseio.com/',
        'storageBucket': 'upload-video-to-android-8930c.appspot.com'
    })

    # Kết nối tới Storage
    bucket = storage.bucket()
    # Gửi lệnh AT để lấy thông tin vị trí GPS hiện tại
    response = send_at_command(com_port, at_command)
    # Tách chuỗi phản hồi để lấy tọa độ (vĩ độ, kinh độ)
    current_location = response.split(',')[0:4]  # Chọn vĩ độ và kinh độ
    current_location.pop(1)  # Xóa phần vĩ độ phút (không cần thiết)
    current_location.pop(2)  # Xóa phần kinh độ phút (không cần thiết)
    # Xử lý chuỗi tọa độ thành định dạng chuẩn
    current_location[0] = process_string(current_location[0])
    current_location[1] = process_string(current_location[1])

    # Lấy tọa độ điểm đến từ Firebase
    destination = get_db_location()
    # Tính khoảng cách giữa vị trí hiện tại và điểm đến
    # Chuyển tọa độ từ chuỗi sang số thực (float) để tính toán
    distance = haversine(float(destination[0]), float(destination[1]), float(current_location[0]), float(current_location[1]))*1000
    peroid = get_time()
    number_of_user = int(check_data_exists('admin/management_user'))
    roll_call = number_of_user*[False]
    emergency = number_of_user*[False]
    for i in range(1,number_of_user+1,1):
        user_id.append(check_data_exists(f"user{i}/id"))
    print(user_id)
    print("Destination:", destination)  # In ra tọa độ điểm đến
    print("Current Location:", current_location)  # In ra tọa độ hiện tại
    print("Distance:",distance, "m")
    print(f"Chênh lệch thời gian là: {peroid} phút")
    if peroid > 0:
        while peroid > 0 and cap.isOpened():
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
                    # print(f"Detected classes: {', '.join(detected_classes)}")
                    common_classes = detected_classes.intersection(user_id)  # Lấy phần tử chung
                    if common_classes:
                        index = user_id.index(''.join(common_classes))+1
                        print(f'user{index}/status')
                        ems = db.reference(f'user{index}/status')
                        ems.set("ems")
                        if emergency[index-1] != True:
                            image_path = f'user{index}_ems.jpg'
                            cv2.imwrite(image_path, frame)
                            blob = bucket.blob(image_path)  # Đường dẫn file trên Firebase Storage
                            blob.upload_from_filename(image_path)
                            blob.make_public()
                            image_url = blob.public_url
                            img = db.reference(f'user{index}/image_path')
                            img.set(f'"{image_url}"')
                            emergency[index-1] = True
                            os.remove(image_path)
                            response = send_at_command(com_port, at_command)
                            # Tách chuỗi phản hồi để lấy tọa độ (vĩ độ, kinh độ)
                            current_location = response.split(',')[0:4]  # Chọn vĩ độ và kinh độ
                            current_location.pop(1)  # Xóa phần vĩ độ phút (không cần thiết)
                            current_location.pop(2)  # Xóa phần kinh độ phút (không cần thiết)
                            # Xử lý chuỗi tọa độ thành định dạng chuẩn
                            current_location[0] = process_string(current_location[0])
                            current_location[1] = process_string(current_location[1])
                            loc = db.reference(f'user{index}/current_location')
                            loc.set(str(current_location))
                            now = str(datetime.now().strftime('%H:%M'))
                            timedb = db.reference(f'user{index}/time')
                            timedb.set(f'"{now}"')

                    else:
                        print("Không có lớp nào trong detected_classes nằm trong user_id")
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
        while peroid < 0 and cap.isOpened():
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
                    # print(f"Detected classes: {', '.join(detected_classes)}")
                    common_classes = detected_classes.intersection(user_id)  # Lấy phần tử chung
                    if common_classes:
                        index = user_id.index(''.join(common_classes))+1
                        print(f'user{index}/status')
                        nor = db.reference(f'user{index}/status')
                        nor.set("nor")
                        if roll_call[index-1] != True:
                            image_path = f'user{index}_rollcall.jpg'
                            cv2.imwrite(image_path, frame)
                            blob = bucket.blob(image_path)  # Đường dẫn file trên Firebase Storage
                            blob.upload_from_filename(image_path)
                            blob.make_public()
                            image_url = blob.public_url
                            img = db.reference(f'user{index}/image_path')
                            img.set(f'"{image_url}"')
                            roll_call[index-1] = True
                            os.remove(image_path)
                            response = send_at_command(com_port, at_command)
                            # Tách chuỗi phản hồi để lấy tọa độ (vĩ độ, kinh độ)
                            current_location = response.split(',')[0:4]  # Chọn vĩ độ và kinh độ
                            current_location.pop(1)  # Xóa phần vĩ độ phút (không cần thiết)
                            current_location.pop(2)  # Xóa phần kinh độ phút (không cần thiết)
                            # Xử lý chuỗi tọa độ thành định dạng chuẩn
                            current_location[0] = process_string(current_location[0])
                            current_location[1] = process_string(current_location[1])
                            loc = db.reference(f'user{index}/current_location')
                            loc.set(str(current_location))
                            now = str(datetime.now().strftime('%H:%M'))
                            timedb = db.reference(f'user{index}/time')
                            timedb.set(f'"{now}"')

                    else:
                        print("Không có lớp nào trong detected_classes nằm trong user_id")
                else:
                    print("No classes detected")
                # Visualize the results on the frame
                annotated_frame = results[0].plot()

                # Display the annotated frame
                cv2.imshow("YOLOv8 Inference", annotated_frame)
                # Break the loop if 'q' is pressed
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    # Kết quả là khoảng cách tính bằng mét
