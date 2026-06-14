def process_morning_streak(sheets_client, emp_name, emp_data, is_late):
    """
    Processes the streak logic during a morning check-in.
    Returns a tuple: (new_streak, achievement_msg)
    """
    curr_streak = int(emp_data.get("Дней подряд", 0) or 0)
    curr_ach = emp_data.get("Текущая ачивка", "")
    
    if is_late:
        # Reset streak
        new_streak = 0
        if curr_streak > 0:
            sheets_client.update_employee_field(emp_name, "Дней подряд", 0)
            sheets_client.update_employee_field(emp_name, "Текущая ачивка", "")
        return new_streak, None
        
    # On time: increment streak
    new_streak = curr_streak + 1
    sheets_client.update_employee_field(emp_name, "Дней подряд", new_streak)
    
    # Check for achievements
    new_ach = curr_ach
    announcement_msg = None
    
    if new_streak == 5:
        new_ach = "Красавчик"
        announcement_msg = f"🏆 **[Ачивка]** **{emp_name}** целую рабочую неделю не опаздывал!\nТы — **Красавчик**! 😎 🥇"
    elif new_streak == 20:
        new_ach = "Супер Красавчик"
        announcement_msg = f"👑 **[Ачивка]** **{emp_name}** целый месяц без опозданий!\nТы — **Супер Красавчик**! 🌟 💎"
    elif new_streak == 60:
        new_ach = "Турбо Красавчик"
        announcement_msg = f"⚡ **[Ачивка]** **{emp_name}** три месяца без единого опоздания!\nТы — **Турбо Красавчик**! 🚀 🔥"
    elif new_streak == 120:
        new_ach = "Супер Турбо Красавчик"
        announcement_msg = f"☄️ **[Ачивка]** **{emp_name}** полгода без единого опоздания!\nТы — **Супер Турбо Красавчик**! 🤯 🦾 🏆"
    elif new_streak == 240:
        new_ach = "Мега Красавчик"
        announcement_msg = f"🌟 **[ЛЕГЕНДА]** **{emp_name}** ЦЕЛЫЙ ГОД без единого опоздания!\nТы — **Мега Красавчик**! 👑 💯 🎊 🍾"
        
    if new_ach != curr_ach:
        sheets_client.update_employee_field(emp_name, "Текущая ачивка", new_ach)
        
    return new_streak, announcement_msg
