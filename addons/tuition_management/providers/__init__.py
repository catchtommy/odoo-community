# -*- coding: utf-8 -*-
from .zoom import ZoomProvider
from .bbb import BBBProvider
from .google_meet import GoogleMeetProvider


PROVIDERS = {
    ZoomProvider.code: ZoomProvider,
    BBBProvider.code: BBBProvider,
    GoogleMeetProvider.code: GoogleMeetProvider,
}
