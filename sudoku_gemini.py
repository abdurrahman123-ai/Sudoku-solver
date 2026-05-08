import tkinter as tk
from tkinter import filedialog, messagebox
import google.generativeai as genai
from pysat.solvers import Glucose3
import PIL.Image
import json
import re
import os
import threading

# ==========================================
# 1.GEMINI API
# ==========================================
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("⚠️ GEMINI_API_KEY not found in environment variables")

genai.configure(api_key=API_KEY)


# ==========================================
# 2.(SAT SOLVER - Multi Solution)
# ==========================================
class SudokuSAT:
    def __init__(self):
        self.solver = Glucose3()
    
    def _to_var(self, r, c, v):
        return (r * 81) + (c * 9) + v

    def _to_grid(self, sat_assignment):
        grid = [[0 for _ in range(9)] for _ in range(9)]
        for var in sat_assignment:
            if var > 0:
                val = (var - 1) % 9 + 1
                temp = (var - 1) // 9
                c = temp % 9
                r = temp // 9
                if 0 <= r < 9 and 0 <= c < 9:
                    grid[r][c] = val
        return grid

    def solve_all(self, initial_grid, max_solutions=100):
        """
        find all posible solutions up to reach max solution number can be found       
        """
        self.solver = Glucose3() 
        
        # 1.add values (Clues)
        for r in range(9):
            for c in range(9):
                val = initial_grid[r][c]
                if val != 0:
                    self.solver.add_clause([self._to_var(r, c, val)])

        # 2.every square can have only 1 value
        for r in range(9):
            for c in range(9):
                self.solver.add_clause([self._to_var(r, c, v) for v in range(1, 10)])

        # (Unique Constraints) defıne conditions
        for v in range(1, 10):
            # repeated number in one row
            for r in range(9):
                for c1 in range(9):
                    for c2 in range(c1 + 1, 9):
                        self.solver.add_clause([-self._to_var(r, c1, v), -self._to_var(r, c2, v)])
            # repeated number in one column
            for c in range(9):
                for r1 in range(9):
                    for r2 in range(r1 + 1, 9):
                        self.solver.add_clause([-self._to_var(r1, c, v), -self._to_var(r2, c, v)])
            # repeated number in small square
            for box_r in range(3):
                for box_c in range(3):
                    cells = []
                    for i in range(3):
                        for j in range(3):
                            cells.append((box_r * 3 + i, box_c * 3 + j))
                    for i in range(len(cells)):
                        for j in range(i + 1, len(cells)):
                            r1, c1 = cells[i]
                            r2, c2 = cells[j]
                            self.solver.add_clause([-self._to_var(r1, c1, v), -self._to_var(r2, c2, v)])

        found_solutions = []
        
        #search all solutions
        while self.solver.solve():
            model = self.solver.get_model()
            solution_grid = self._to_grid(model)
            found_solutions.append(solution_grid)
            
            # if there are more than 100 solitions
            if len(found_solutions) >= max_solutions:
                break
            
            # الشرط السحري: Blocking Clause
            # نقول للمحرك: الحل القادم يجب ألا يكون مطابقاً لهذا الحل (نفي النموذج الحالي)
            self.solver.add_clause([-lit for lit in model])
            
        return found_solutions

# ==========================================
# 3. منطق قراءة الصورة (Gemini) - النسخة المصححة للواجهة
# ==========================================
# ==========================================
# 3. منطق قراءة الصورة (Gemini) - نظام الإحداثيات (JSON Coordinates)
# هذا النظام هو الأفضل للصور التي تحتوي على فراغات كثيرة أو خطوط باهتة
# ==========================================
def extract_sudoku_from_image(image_path):
    try:
        img = PIL.Image.open(image_path)
        # نستخدم Pro لأنه أذكى في تحديد المواقع
        model = genai.GenerativeModel('gemini-flash-latest')
        
        prompt = """
        You are a Sudoku coordinate extractor.
        Your task is to identify every visible number in the grid and report its position.

        OUTPUT FORMAT:
        Return ONLY a JSON list of objects. Each object must have:
        - "val": The number (1-9).
        - "row": The row number (1-9, from top to bottom).
        - "col": The column number (1-9, from left to right).

        RULES:
        1. Ignore empty cells. Do NOT output anything for them.
        2. Be extremely precise with "row" and "col". Use the grid lines as guides.
        3. Row 1 is the very top row. Row 9 is the very bottom.
        4. Col 1 is the far left. Col 9 is the far right.
        
        Example JSON Structure:
        [
          {"val": 5, "row": 1, "col": 3},
          {"val": 9, "row": 2, "col": 5}
        ]
        """
        
        response = model.generate_content([prompt, img])
        text = response.text.strip()
        
        # تنظيف النص من علامات الكود (Markdown)
        if text.startswith(""):
            text = re.sub(r"^json|^|$", "", text, flags=re.MULTILINE).strip()
            
        # تحويل النص إلى قائمة
        data = json.loads(text)
        
        # 1. ننشئ مصفوفة فارغة تماماً (أصفار) في بايثون
        # هذا يضمن أن الأبعاد دائماً صحيحة (9x9)
        matrix = [[0 for _ in range(9)] for _ in range(9)]
        
        # 2. نملأ المصفوفة بناءً على الإحداثيات التي وجدها جيميني
        for item in data:
            try:
                r = int(item.get('row')) - 1  # ننقص 1 لأن بايثون يبدأ من 0
                c = int(item.get('col')) - 1
                v = int(item.get('val'))
                
                # التحقق من أن الإحداثيات داخل الحدود
                if 0 <= r < 9 and 0 <= c < 9:
                    matrix[r][c] = v
            except (ValueError, TypeError):
                continue # نتجاهل أي قيم تالفة

        # طباعة للمراقبة في التيرمينال
        print("--- المصفوفة المستخرجة ---")
        for row in matrix:
            print(row)
            
        return matrix

    except json.JSONDecodeError:
        print("فشل في قراءة JSON من Gemini.")
        print("النص المستلم:", text) # للتشخيص
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

# ==========================================
# 4. واجهة المستخدم (GUI)
# ==========================================
class SudokuApp:
    def __init__(self, root):

        self.root = root

        self.root.title("Multi-Solution Sudoku Solver")
        self.cells = {} 
        self.solutions = [] # قائمة لحفظ جميع الحلول
        self.current_sol_idx = 0
        
        # بناء الشبكة
        self.create_grid()
        
        # أزرار التحكم الرئيسية
        control_frame = tk.Frame(root)
        control_frame.pack(pady=10)
        
        self.btn_load = tk.Button(control_frame, text="📷 تحميل صورة", command=self.load_image_thread, bg="#dddddd")
        self.btn_load.pack(side=tk.LEFT, padx=5)
        
        self.btn_solve = tk.Button(control_frame, text="🔍 إيجاد كل الحلول", command=self.solve_puzzle, bg="#4CAF50", fg="white", font=("Arial", 11, "bold"))
        self.btn_solve.pack(side=tk.LEFT, padx=5)
        
        self.btn_clear = tk.Button(control_frame, text="🗑 مسح", command=self.clear_grid, bg="#ffcccc")
        self.btn_clear.pack(side=tk.LEFT, padx=5)

        # شريط التنقل بين الحلول (مخفي في البداية)
        self.nav_frame = tk.Frame(root, bg="#f0f0f0", bd=2, relief=tk.GROOVE)
        
        self.btn_prev = tk.Button(self.nav_frame, text="< السابق", command=self.prev_solution, state=tk.DISABLED)
        self.btn_prev.pack(side=tk.LEFT, padx=10)
        
        self.lbl_sol_count = tk.Label(self.nav_frame, text="الحل 0 من 0", font=("Arial", 10, "bold"), bg="#f0f0f0")
        self.lbl_sol_count.pack(side=tk.LEFT, padx=10)
        
        self.btn_next = tk.Button(self.nav_frame, text="التالي >", command=self.next_solution, state=tk.DISABLED)
        self.btn_next.pack(side=tk.LEFT, padx=10)

        # شريط الحالة
        self.status_label = tk.Label(root, text="جاهز", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def create_grid(self):
        grid_frame = tk.Frame(self.root, bg="black", bd=2)
        grid_frame.pack(padx=20, pady=20)
        
        for r in range(9):
            for c in range(9):
                pad_top = 2 if r % 3 == 0 and r != 0 else 0.5
                pad_left = 2 if c % 3 == 0 and c != 0 else 0.5
                cell_frame = tk.Frame(grid_frame, bg="white", width=45, height=45)
                cell_frame.grid(row=r, column=c, padx=(pad_left, 0.5), pady=(pad_top, 0.5))
                
                entry = tk.Entry(cell_frame, width=2, font=("Arial", 16, "bold"), justify="center", bd=0)
                entry.pack(fill="both", expand=True)
                self.cells[(r, c)] = entry

    def load_image_thread(self):
        file_path = filedialog.askopenfilename(filetypes=[("Images", ".jpg;.jpeg;*.png")])
        if not file_path: return
        self.status_label.config(text="جاري تحليل الصورة...")
        thread = threading.Thread(target=self.process_image, args=(file_path,))
        thread.start()

    def process_image(self, file_path):
        matrix = extract_sudoku_from_image(file_path)
        if matrix:
            self.root.after(0, lambda: self.fill_initial_grid(matrix))
        else:
            self.root.after(0, lambda: messagebox.showerror("خطأ", "فشل تحليل الصورة."))

    def fill_initial_grid(self, matrix):
        self.clear_grid()
        for r in range(9):
            for c in range(9):
                val = matrix[r][c]
                if val != 0:
                    self.cells[(r, c)].insert(0, str(val))
                    self.cells[(r, c)].config(fg="blue")
        self.status_label.config(text="تم تحميل الأرقام. اضغط 'إيجاد كل الحلول'.")

    def clear_grid(self):
        self.solutions = []
        self.nav_frame.pack_forget() # إخفاء أزرار التنقل
        for r in range(9):
            for c in range(9):
                self.cells[(r, c)].delete(0, tk.END)
                self.cells[(r, c)].config(fg="black", bg="white")
        self.status_label.config(text="جاهز")

    def get_grid_values(self):
        matrix = [[0]*9 for _ in range(9)]
        try:
            for r in range(9):
                for c in range(9):
                    text = self.cells[(r, c)].get()
                    if text.strip():
                        val = int(text)
                        if 1 <= val <= 9:
                            matrix[r][c] = val
                        else:
                            raise ValueError
            return matrix
        except ValueError:
            messagebox.showwarning("خطأ", "أدخل أرقاماً صحيحة فقط (1-9)")
            return None

    def solve_puzzle(self):
        initial_grid = self.get_grid_values()
        if not initial_grid: return
            
        self.status_label.config(text="جاري البحث عن جميع الحلول...")
        self.root.update()
        
        solver = SudokuSAT()
        # حد أقصى للحلول 100 لتجنب التجمد في حال كانت الشبكة فارغة تماماً
        found_solutions = solver.solve_all(initial_grid, max_solutions=100)
        
        if not found_solutions:
            messagebox.showerror("خطأ", "هذه السودوكو مستحيلة الحل (Unsolvable)!")
            self.status_label.config(text="مستحيلة الحل")
            self.nav_frame.pack_forget()
        else:
            self.solutions = found_solutions
            self.current_sol_idx = 0
            self.show_solution(0)
            
            # إظهار أزرار التنقل
            self.nav_frame.pack(pady=5)
            self.update_nav_buttons()
            
            msg = f"تم العثور على {len(found_solutions)} حل/حلول."
            if len(found_solutions) >= 100:
                msg += " (تم التوقف عند الحد الأقصى)."
            self.status_label.config(text=msg)
            
            if len(found_solutions) > 1:
                messagebox.showinfo("نجاح", f"تم العثور على {len(found_solutions)} حلول مختلفة!\nاستخدم أزرار التنقل في الأسفل لاستعراضها.")

    def show_solution(self, idx):
        grid = self.solutions[idx]
        initial_grid = self.get_grid_values() # نحتاج معرفة ما أدخله المستخدم لتمييزه
        
        for r in range(9):
            for c in range(9):
                # لا نغير الأرقام التي أدخلها المستخدم (باللون الأزرق)
                # نغير فقط الخانات التي كانت فارغة أو محسوبة
                is_user_input = (self.cells[(r, c)].cget('fg') == 'blue')
                
                if not is_user_input:
                    self.cells[(r, c)].delete(0, tk.END)
                    self.cells[(r, c)].insert(0, str(grid[r][c]))
                    self.cells[(r, c)].config(fg="green") # الحلول باللون الأخضر

    def next_solution(self):
        if self.current_sol_idx < len(self.solutions) - 1:
            self.current_sol_idx += 1
            self.show_solution(self.current_sol_idx)
            self.update_nav_buttons()

    def prev_solution(self):
        if self.current_sol_idx > 0:
            self.current_sol_idx -= 1
            self.show_solution(self.current_sol_idx)
            self.update_nav_buttons()

    def update_nav_buttons(self):
        total = len(self.solutions)
        current = self.current_sol_idx + 1
        self.lbl_sol_count.config(text=f"الحل {current} من {total}")
        
        if current == 1:
            self.btn_prev.config(state=tk.DISABLED)
        else:
            self.btn_prev.config(state=tk.NORMAL)
            
        if current == total:
            self.btn_next.config(state=tk.DISABLED)
        else:
            self.btn_next.config(state=tk.NORMAL)

# ==========================================
# تشغيل التطبيق
# ==========================================
if __name__ == "_main_":
    if API_KEY == "ضع_مفتاح_API_الخاص_بك_هنا":
        print("تنبيه: لا تنس وضع مفتاح API")
    
    root = tk.Tk()
    w, h = 500, 650
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws/2) - (w/2)
    y = (hs/2) - (h/2)
    root.geometry('%dx%d+%d+%d' % (w, h, x, y))
    
    app = SudokuApp(root)
    root.mainloop()