"""Numeric evidence for a PS1 resume-button press and returning 3D picture.

A stale GPU flip counter or renderer increment is not a new visible picture.
The PRIMARY pause-image linger is the time from button press to the first
newly changed city picture, even if the guest clock resumes later. Continue
sampling to detect intermittent picture stalls after that first return.
"""


class ResumeEvidence:
    def __init__(self, start_frame, pause_image_hash, pause_clock,
                 pause_flip, pause_renderer):
        self.start_frame = start_frame
        self.pause_image_hash = pause_image_hash
        self.pause_clock = pause_clock
        self.pause_flip = pause_flip
        self.pause_renderer = pause_renderer
        self.previous_hash = pause_image_hash
        self.previous_flip = pause_flip
        self.previous_renderer = pause_renderer
        self.post_new_frame_samples = 0
        self.post_new_frame_picture_changes = 0
        self.post_new_frame_max_static_frames = 0
        self._static_start = None
        self._static_end = None
        self._static_runs = []
        self.events = {k: None for k in (
            'clock_restarted', 'first_any_picture_change',
            'first_new_picture', 'first_gpu_flip',
            'first_3d_render', 'first_playable_picture')}

    def _finish_static_run(self):
        if self._static_start is not None:
            duration = self._static_end - self._static_start + 1
            if duration >= 2 and len(self._static_runs) < 25:
                self._static_runs.append({
                    'start_after_press': self._static_start - self.start_frame,
                    'end_after_press': self._static_end - self.start_frame,
                    'static_frames': duration,
                })
        self._static_start = self._static_end = None

    def sample(self, frame, clock, image_hash, display_flips, rendered_3d,
               looks_like_city):
        if frame < self.start_frame:
            raise ValueError('frame_before_resume_press')

        # Check the immediately previous sampled frame, NOT the pause baseline
        # alone. Otherwise a counter that stepped on an unchanged pause image
        # would be misreported as a visible display flip/render at stock.
        changed = (image_hash is not None and self.previous_hash is not None
                   and image_hash != self.previous_hash)
        new_picture = changed and image_hash != self.pause_image_hash
        new_city_picture = new_picture and looks_like_city
        flip_changed = (display_flips is not None and self.previous_flip is not None
                        and display_flips != self.previous_flip)
        render_changed = (rendered_3d is not None and self.previous_renderer is not None
                          and rendered_3d != self.previous_renderer)

        if self.events['clock_restarted'] is None and clock > self.pause_clock:
            self.events['clock_restarted'] = frame
        if new_picture and self.events['first_any_picture_change'] is None:
            self.events['first_any_picture_change'] = frame
        if new_city_picture and self.events['first_new_picture'] is None:
            self.events['first_new_picture'] = frame
        if new_city_picture and flip_changed and self.events['first_gpu_flip'] is None:
            self.events['first_gpu_flip'] = frame
        if new_city_picture and render_changed and self.events['first_3d_render'] is None:
            self.events['first_3d_render'] = frame
        if (new_city_picture and self.events['first_playable_picture'] is None
                and self.events['clock_restarted'] is not None
                and self.events['first_gpu_flip'] is not None
                and self.events['first_3d_render'] is not None):
            self.events['first_playable_picture'] = frame

        first = self.events['first_new_picture']
        if first is not None and frame > first:
            self.post_new_frame_samples += 1
            if changed:
                self.post_new_frame_picture_changes += 1
                self._finish_static_run()
            else:
                if self._static_start is None:
                    self._static_start = frame
                self._static_end = frame
                self.post_new_frame_max_static_frames = max(
                    self.post_new_frame_max_static_frames,
                    frame - self._static_start + 1)

        if image_hash is not None:
            self.previous_hash = image_hash
        if display_flips is not None:
            self.previous_flip = display_flips
        if rendered_3d is not None:
            self.previous_renderer = rendered_3d

    def summary(self):
        values = dict(self.events)
        first = values['first_new_picture']
        clock = values['clock_restarted']
        playable = values['first_playable_picture']
        press_lag = first - self.start_frame if first is not None else None
        # Release gate uses this press-to-picture delay, not the clock offset.
        values['visible_linger_after_resume_press_frames'] = press_lag
        values['first_new_picture_after_press_frames'] = press_lag
        values['first_playable_picture_after_press_frames'] = (
            playable - self.start_frame if playable is not None else None)
        values['visible_linger_after_clock_restart_frames'] = (
            playable - clock if playable is not None and clock is not None else None)
        values['post_new_frame_observed_frames'] = self.post_new_frame_samples
        values['post_new_frame_picture_changes'] = self.post_new_frame_picture_changes
        values['post_new_frame_max_static_frames'] = self.post_new_frame_max_static_frames
        runs = list(self._static_runs)
        if self._static_start is not None:
            duration = self._static_end - self._static_start + 1
            if duration >= 2 and len(runs) < 25:
                runs.append({
                    'start_after_press': self._static_start - self.start_frame,
                    'end_after_press': self._static_end - self.start_frame,
                    'static_frames': duration,
                })
        values['post_new_frame_still_intervals'] = runs
        return values
