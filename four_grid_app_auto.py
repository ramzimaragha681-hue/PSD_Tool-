from pathlib import Path
from psd_tools import PSDImage
from PIL import Image, ImageOps
import math
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


IMAGE_EXTS = {".jpg", ".jpeg"}

# 默认按图层名自动识别
TARGET_LAYER_NAMES = ["左上", "右上", "左下", "右下"]


def find_layers_by_name(psd, target_names):
    """
    自动识别 PSD 中指定名称的图层，并返回对应坐标。
    需要 PSD 图层名包含：左上、右上、左下、右下
    返回格式：
    {
        "左上": (left, top, right, bottom),
        "右上": (left, top, right, bottom),
        ...
    }
    """
    result = {}

    def walk(layers):
        for layer in layers:
            name = str(layer.name).strip()

            if name in target_names:
                result[name] = (layer.left, layer.top, layer.right, layer.bottom)

            if layer.is_group():
                walk(layer)

    walk(psd)
    return result


def auto_get_boxes(psd, log_func):
    """
    自动获取四个照片区域坐标。
    优先按图层名识别：左上、右上、左下、右下。
    """
    found = find_layers_by_name(psd, TARGET_LAYER_NAMES)

    missing = [name for name in TARGET_LAYER_NAMES if name not in found]
    if missing:
        raise ValueError(
            "PSD 模板中没有找到这些图层："
            + "、".join(missing)
            + "\n请把 PSD 中四个照片图层命名为：左上、右上、左下、右下"
        )

    boxes = [found[name] for name in TARGET_LAYER_NAMES]

    log_func("已自动识别 PSD 图层坐标：")
    for name, box in zip(TARGET_LAYER_NAMES, boxes):
        left, top, right, bottom = box
        log_func(
            f"{name}: left={left}, top={top}, right={right}, bottom={bottom}, "
            f"尺寸={right-left}x{bottom-top}"
        )

    return boxes


def resize_before_replace(img_path, target_w, target_h):
    """
    替换前处理图片大小：
    1. 读取 JPG
    2. 修正手机照片 EXIF 旋转
    3. 转为 RGB
    4. 按目标框尺寸居中裁剪并缩放
    """
    img = Image.open(img_path)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")

    resized = ImageOps.fit(
        img,
        (target_w, target_h),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )

    return resized


def replace_images(psd_path, input_dir, output_dir, log_func):
    psd_path = Path(psd_path)
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    if not psd_path.exists():
        raise FileNotFoundError(f"找不到 PSD 文件：{psd_path}")

    if not input_dir.exists():
        raise FileNotFoundError(f"找不到照片文件夹：{input_dir}")

    images = sorted([
        p for p in input_dir.iterdir()
        if p.suffix.lower() in IMAGE_EXTS
    ])

    if not images:
        raise FileNotFoundError("照片文件夹里没有找到 JPG/JPEG 图片。")

    log_func("正在读取 PSD 模板...")
    psd = PSDImage.open(psd_path)

    boxes = auto_get_boxes(psd, log_func)

    total_groups = math.ceil(len(images) / 4)
    log_func(f"共找到 {len(images)} 张照片，将生成 {total_groups} 张四宫格。")

    for group_index in range(total_groups):
        log_func(f"正在生成第 {group_index + 1} 张四宫格...")

        canvas = psd.composite().convert("RGB")
        group = images[group_index * 4: group_index * 4 + 4]

        for i, img_path in enumerate(group):
            left, top, right, bottom = boxes[i]
            target_w = right - left
            target_h = bottom - top

            new_img = resize_before_replace(img_path, target_w, target_h)
            canvas.paste(new_img, (left, top))

            log_func(
                f"{img_path.name} -> {TARGET_LAYER_NAMES[i]}，"
                f"尺寸 {target_w}x{target_h}"
            )

        output_file = output_dir / f"replace_{group_index + 1:03d}.jpg"

        canvas.save(
            output_file,
            "JPEG",
            quality=95,
            optimize=True
        )

        log_func(f"已生成：{output_file}")

    log_func("全部完成。")


class FourGridApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PSD四宫格批量替换工具 - 自动识别版")
        self.root.geometry("820x570")
        self.root.resizable(False, False)

        self.psd_var = tk.StringVar()
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()

        self.build_ui()

    def build_ui(self):
        title = tk.Label(
            self.root,
            text="PSD四宫格批量替换工具",
            font=("Microsoft YaHei", 18, "bold")
        )
        title.pack(pady=14)

        subtitle = tk.Label(
            self.root,
            text="自动识别 PSD 中的“左上、右上、左下、右下”图层，并批量替换 JPG 照片",
            font=("Microsoft YaHei", 10),
            fg="#555555"
        )
        subtitle.pack(pady=2)

        frame = tk.Frame(self.root)
        frame.pack(fill="x", padx=22, pady=8)

        self.add_path_row(frame, "PSD模板：", self.psd_var, self.select_psd, 0)
        self.add_path_row(frame, "照片文件夹：", self.input_var, self.select_input, 1)
        self.add_path_row(frame, "输出文件夹：", self.output_var, self.select_output, 2)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=8)

        self.start_btn = tk.Button(
            btn_frame,
            text="开始生成",
            font=("Microsoft YaHei", 12, "bold"),
            width=16,
            height=2,
            command=self.start
        )
        self.start_btn.grid(row=0, column=0, padx=8)

        self.clear_btn = tk.Button(
            btn_frame,
            text="清空日志",
            font=("Microsoft YaHei", 10),
            width=10,
            height=2,
            command=self.clear_log
        )
        self.clear_btn.grid(row=0, column=1, padx=8)

        tip = tk.Label(
            self.root,
            text="要求：PSD 中四个待替换图层必须命名为 左上、右上、左下、右下；输入照片为 JPG/JPEG。",
            font=("Microsoft YaHei", 10),
            fg="#8A0000"
        )
        tip.pack(pady=4)

        self.log_box = scrolledtext.ScrolledText(
            self.root,
            width=104,
            height=18,
            font=("Consolas", 10)
        )
        self.log_box.pack(padx=22, pady=10)

    def add_path_row(self, parent, label_text, var, command, row):
        label = tk.Label(
            parent,
            text=label_text,
            font=("Microsoft YaHei", 10),
            width=12,
            anchor="e"
        )
        label.grid(row=row, column=0, pady=8, sticky="e")

        entry = tk.Entry(parent, textvariable=var, width=78)
        entry.grid(row=row, column=1, padx=8, pady=8)

        button = tk.Button(parent, text="选择", command=command, width=8)
        button.grid(row=row, column=2, pady=8)

    def select_psd(self):
        path = filedialog.askopenfilename(
            title="选择 PSD 模板",
            filetypes=[("PSD 文件", "*.psd"), ("所有文件", "*.*")]
        )
        if path:
            self.psd_var.set(path)
            self.log(f"已选择 PSD 模板：{path}")

    def select_input(self):
        path = filedialog.askdirectory(title="选择照片输入文件夹")
        if path:
            self.input_var.set(path)
            self.log(f"已选择照片文件夹：{path}")

    def select_output(self):
        path = filedialog.askdirectory(title="选择输出文件夹")
        if path:
            self.output_var.set(path)
            self.log(f"已选择输出文件夹：{path}")

    def log(self, text):
        self.log_box.insert(tk.END, text + "\n")
        self.log_box.see(tk.END)
        self.root.update_idletasks()

    def clear_log(self):
        self.log_box.delete("1.0", tk.END)

    def start(self):
        psd_path = self.psd_var.get().strip()
        input_dir = self.input_var.get().strip()
        output_dir = self.output_var.get().strip()

        if not psd_path:
            messagebox.showwarning("提示", "请选择 PSD 模板。")
            return

        if not input_dir:
            messagebox.showwarning("提示", "请选择照片文件夹。")
            return

        if not output_dir:
            messagebox.showwarning("提示", "请选择输出文件夹。")
            return

        self.start_btn.config(state="disabled")
        self.log("开始处理...")

        thread = threading.Thread(
            target=self.run_task,
            args=(psd_path, input_dir, output_dir),
            daemon=True
        )
        thread.start()

    def run_task(self, psd_path, input_dir, output_dir):
        try:
            replace_images(psd_path, input_dir, output_dir, self.log)
            messagebox.showinfo("完成", "四宫格 JPG 已全部生成。")
        except Exception as e:
            messagebox.showerror("错误", str(e))
            self.log(f"错误：{e}")
        finally:
            self.start_btn.config(state="normal")


def main():
    root = tk.Tk()
    app = FourGridApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()