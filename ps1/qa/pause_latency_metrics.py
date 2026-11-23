"""Pure numeric evidence about a PS1 pause -> gameplay transition.

A picture is considered a newly returned 3D view only after the guest clock
has restarted AND a new renderer frame, display flip and visible city picture
have all been observed. This avoids treating a still image or a menu fade as
proof of an actually playable resumed view.
"""


class ResumeEvidence:
    def __init__(self, start_frame, pause_image_hash, pause_clock,
                 pause_flip, pause_renderer):
        self.start_frame = start_frame
        self.pause_image_hash = pause_image_hash
        self.pause_clock = pause_clock
        self.pause_flip = pause_flip
        self.pause_renderer = pause_renderer
        self.events = {k: None for k in (
            'clock_restarted', 'first_new_picture', 'first_gpu_flip',
            'first_3d_render', 'first_playable_picture')}

    def sample(self, frame, clock, image_hash, display_flips, rendered_3d,
               looks_like_city):
        if frame < self.start_frame:
            raise ValueError('frame_before_resume_press')
        if self.events['clock_restarted'] is None and clock > self.pause_clock:
            self.events['clock_restarted'] = frame
        if (self.events['first_new_picture'] is None and image_hash is not None
                and image_hash != self.pause_image_hash):
            self.events['first_new_picture'] = frame
        if (self.events['first_gpu_flip'] is None and display_flips is not None
                and self.pause_flip is not None and display_flips != self.pause_flip):
            self.events['first_gpu_flip'] = frame
        if (self.events['first_3d_render'] is None and rendered_3d is not None
                and self.pause_renderer is not None
                and rendered_3d != self.pause_renderer):
            self.events['first_3d_render'] = frame
        if (self.events['first_playable_picture'] is None and looks_like_city
                and self.events['clock_restarted'] is not None
                and self.events['first_new_picture'] is not None
                and self.events['first_gpu_flip'] is not None
                and self.events['first_3d_render'] is not None):
            self.events['first_playable_picture'] = frame

    def summary(self):
        values = dict(self.events)
        resumed_at = values['clock_restarted']
        picture_at = values['first_playable_picture']
        values['first_playable_picture_after_press_frames'] = (
            picture_at - self.start_frame if picture_at is not None else None)
        values['visible_linger_after_clock_restart_frames'] = (
            picture_at - resumed_at
            if picture_at is not None and resumed_at is not None else None)
        return values