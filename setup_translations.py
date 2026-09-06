"""
Script to set up translations for the Fuel Tank Monitoring System
"""
import os
import json

# Create translations directory if it doesn't exist
os.makedirs('translations/en/LC_MESSAGES', exist_ok=True)
os.makedirs('translations/ar/LC_MESSAGES', exist_ok=True)

# Create English translation file
en_translations = {
    # General UI
    "Dashboard": "Dashboard",
    "Tanks Overview": "Tanks Overview",
    "Tank Details": "Tank Details",
    "Reports": "Reports",
    "Settings": "Settings",
    "Alarms": "Alarms",
    "Login": "Login",
    "Logout": "Logout",
    "Profile": "Profile",
    "Admin": "Admin",
    "Home": "Home",
    
    # Time expressions
    "Just now": "Just now",
    "%(minutes)d minute%(plural)s ago": "%(minutes)d minute%(plural)s ago",
    "%(hours)d hour%(plural)s ago": "%(hours)d hour%(plural)s ago",
    "%(days)d day%(plural)s ago": "%(days)d day%(plural)s ago",
    
    # Status messages
    "Access denied": "Access denied",
    "No measurement available": "No measurement available",
    "unknown": "unknown",
    "critical": "critical",
    "low": "low",
    "high": "high",
    "normal": "normal",
    "Connected": "Connected",
    "Disconnected": "Disconnected",
    "Error": "Error",
    
    # Error pages
    "Page Not Found": "Page Not Found",
    "Server Error": "Server Error",
    
    # API messages
    "Connected to tank updates stream": "Connected to tank updates stream",
    "Tank not accessible": "Tank not accessible",
    "Invalid days parameter": "Invalid days parameter",
    
    # Measurement units and labels
    "Timestamp": "Timestamp",
    "Pressure (bar)": "Pressure (bar)",
    "Temperature (°C)": "Temperature (°C)",
    "Level (m)": "Level (m)",
    "Volume (L)": "Volume (L)",
    "Flow Rate (L/min)": "Flow Rate (L/min)",
    "Fill (%)": "Fill (%)",
    "Status": "Status",
    
    # Form labels
    "Username": "Username",
    "Password": "Password",
    "Remember Me": "Remember Me",
    "Email": "Email",
    "First Name": "First Name",
    "Last Name": "Last Name",
    "Phone": "Phone",
    "Address": "Address",
    "Company": "Company",
    "Site": "Site",
    "Tank": "Tank",
    
    # Buttons
    "Save": "Save",
    "Cancel": "Cancel",
    "Delete": "Delete",
    "Edit": "Edit",
    "Create": "Create",
    "Update": "Update",
    "Submit": "Submit",
    "Search": "Search",
    "Filter": "Filter",
    "Clear": "Clear",
    "Download": "Download",
    "Upload": "Upload",
    
    # Success messages
    "Changes saved successfully": "Changes saved successfully",
    "Calibration updated successfully": "Calibration updated successfully",
    "Alarm acknowledged": "Alarm acknowledged",
    
    # Tank monitoring
    "Tank Level": "Tank Level",
    "Current Volume": "Current Volume",
    "Maximum Volume": "Maximum Volume",
    "Last Updated": "Last Updated",
    "Consumption Rate": "Consumption Rate",
    "Estimated Days Remaining": "Estimated Days Remaining",
    "Historical Data": "Historical Data",
    "Forecast": "Forecast",
    "Calibration": "Calibration",
    "Tank Height": "Tank Height",
    "Tank Diameter": "Tank Diameter",
    "Fluid Density": "Fluid Density",
    "Atmospheric Pressure": "Atmospheric Pressure",
    "Calibration Factor": "Calibration Factor",
    
    # Fuel Tank Monitoring System
    "Fuel Tank Monitoring System": "Fuel Tank Monitoring System",
    "© 2023 Fuel Tank Monitoring System": "© 2023 Fuel Tank Monitoring System"
}

# Create Arabic translation file
ar_translations = {
    # General UI
    "Dashboard": "لوحة القيادة",
    "Tanks Overview": "نظرة عامة على الخزانات",
    "Tank Details": "تفاصيل الخزان",
    "Reports": "التقارير",
    "Settings": "الإعدادات",
    "Alarms": "الإنذارات",
    "Login": "تسجيل الدخول",
    "Logout": "تسجيل الخروج",
    "Profile": "الملف الشخصي",
    "Admin": "المسؤول",
    "Home": "الرئيسية",
    
    # Time expressions
    "Just now": "الآن",
    "%(minutes)d minute%(plural)s ago": "منذ %(minutes)d دقيقة%(plural)s",
    "%(hours)d hour%(plural)s ago": "منذ %(hours)d ساعة%(plural)s",
    "%(days)d day%(plural)s ago": "منذ %(days)d يوم%(plural)s",
    
    # Status messages
    "Access denied": "تم رفض الوصول",
    "No measurement available": "لا توجد قياسات متاحة",
    "unknown": "غير معروف",
    "critical": "حرج",
    "low": "منخفض",
    "high": "مرتفع",
    "normal": "طبيعي",
    "Connected": "متصل",
    "Disconnected": "غير متصل",
    "Error": "خطأ",
    
    # Error pages
    "Page Not Found": "الصفحة غير موجودة",
    "Server Error": "خطأ في الخادم",
    
    # API messages
    "Connected to tank updates stream": "متصل بتحديثات الخزان",
    "Tank not accessible": "الخزان غير متاح",
    "Invalid days parameter": "معلمة الأيام غير صالحة",
    
    # Measurement units and labels
    "Timestamp": "الطابع الزمني",
    "Pressure (bar)": "الضغط (بار)",
    "Temperature (°C)": "درجة الحرارة (°م)",
    "Level (m)": "المستوى (م)",
    "Volume (L)": "الحجم (لتر)",
    "Flow Rate (L/min)": "معدل التدفق (لتر/دقيقة)",
    "Fill (%)": "الملء (%)",
    "Status": "الحالة",
    
    # Form labels
    "Username": "اسم المستخدم",
    "Password": "كلمة المرور",
    "Remember Me": "تذكرني",
    "Email": "البريد الإلكتروني",
    "First Name": "الاسم الأول",
    "Last Name": "اسم العائلة",
    "Phone": "الهاتف",
    "Address": "العنوان",
    "Company": "الشركة",
    "Site": "الموقع",
    "Tank": "الخزان",
    
    # Buttons
    "Save": "حفظ",
    "Cancel": "إلغاء",
    "Delete": "حذف",
    "Edit": "تعديل",
    "Create": "إنشاء",
    "Update": "تحديث",
    "Submit": "إرسال",
    "Search": "بحث",
    "Filter": "تصفية",
    "Clear": "مسح",
    "Download": "تنزيل",
    "Upload": "رفع",
    
    # Success messages
    "Changes saved successfully": "تم حفظ التغييرات بنجاح",
    "Calibration updated successfully": "تم تحديث المعايرة بنجاح",
    "Alarm acknowledged": "تم الإقرار بالإنذار",
    
    # Tank monitoring
    "Tank Level": "مستوى الخزان",
    "Current Volume": "الحجم الحالي",
    "Maximum Volume": "الحجم الأقصى",
    "Last Updated": "آخر تحديث",
    "Consumption Rate": "معدل الاستهلاك",
    "Estimated Days Remaining": "الأيام المتبقية المقدرة",
    "Historical Data": "البيانات التاريخية",
    "Forecast": "التنبؤ",
    "Calibration": "المعايرة",
    "Tank Height": "ارتفاع الخزان",
    "Tank Diameter": "قطر الخزان",
    "Fluid Density": "كثافة السائل",
    "Atmospheric Pressure": "الضغط الجوي",
    "Calibration Factor": "عامل المعايرة",
    
    # Fuel Tank Monitoring System
    "Fuel Tank Monitoring System": "نظام مراقبة خزان الوقود",
    "© 2023 Fuel Tank Monitoring System": "© 2023 نظام مراقبة خزان الوقود"
}

# Write English translations to JSON file
with open('translations/en/LC_MESSAGES/messages.json', 'w', encoding='utf-8') as f:
    json.dump(en_translations, f, ensure_ascii=False, indent=2)

# Write Arabic translations to JSON file
with open('translations/ar/LC_MESSAGES/messages.json', 'w', encoding='utf-8') as f:
    json.dump(ar_translations, f, ensure_ascii=False, indent=2)

print("Translation files created successfully!")