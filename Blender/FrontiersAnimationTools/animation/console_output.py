import bpy
import time


# Manage console output and status for better visibility on import/export progress during UI freeze
class BatchProgress:
    def __init__(self, self_pass, num_items=0, num_frames=0, method='IMPORT'):
        self.num_files = num_items
        self.num_frames = num_frames
        self.status_len = 0
        self.status = ""
        self.error_list = []
        if method:
            self.method = method
        else:
            self.method = None
        self.start_time = time.time()
        self.self_pass = self_pass
        self.item_num = 0
        self.item_name = str()

        if self.method == 'IMPORT':
            print("Importing PXD animations...")
        elif self.method == 'EXPORT':
            print("Exporting PXD Animations...")

    def update_frame_count(self, num_frames):
        self.num_frames = num_frames

    def resume(self, frame_num=0, name=str(), item_num=0):
        if item_num:
            self.item_num = item_num
        if name:
            self.item_name = name

        if self.method == 'IMPORT':
            status = f"{self.item_num + 1} / {self.num_files}\t{self.item_name}\t{frame_num + 1} / {self.num_frames}"
        elif self.method == 'EXPORT':
            status = f"{self.item_num + 1} / {self.num_files}\t{self.item_name}"
        print(' ' * self.status_len, end=f'\r{status}\r')
        self.status_len = len(status) + 32

    def update_error(self, name=str(), error=None):
        if name != str():
            self.item_name = name
        self.error_list.append(self.item_name)
        if self.method == 'IMPORT':
            self.self_pass.report({'ERROR'}, f"{self.item_name}: {error}")
            self.self_pass.report({'WARNING'}, f"{self.item_name} import was skipped due to errors.")

        elif self.method == 'EXPORT':
            self.self_pass.report({'WARNING'}, f"{self.item_name} export was aborted due to errors.")

    def finish(self):
        if self.method == 'IMPORT':
            if self.error_list:
                self.self_pass.report({'INFO'}, "Some animations were skipped due to errors. Please see console for list of skipped animations.")
                for anim in self.error_list:
                    print(anim)
            else:
                self.self_pass.report({'INFO'}, "All animations imported successfully.")

            # Finish single line status printing
            end_time = time.time()
            time_elapsed = end_time - self.start_time
            print(' ' * self.status_len, end=f"\rFinished importing {self.num_files} animations in {round(time_elapsed, 2)} seconds.\n")

        elif self.method == 'EXPORT':
            if self.error_list:
                self.self_pass.report({'INFO'}, "Some animations were skipped due to errors. Please see console for list of skipped animations.")
                for anim in self.error_list:
                    print(anim)
            else:
                self.self_pass.report({'INFO'}, "All animations exported successfully.")

            print(' ' * self.status_len, end=f"\rFinished exporting {self.num_files - len(self.error_list)} animations.\n")
