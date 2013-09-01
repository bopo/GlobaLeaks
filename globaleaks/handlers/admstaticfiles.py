# -*- coding: utf-8 -*-
#
#  admstaticfiles
#  **************
#
# Backend supports for jQuery File Uploader, and implementation of the
# file statically uploaded by the Admin, and exposed after in http://NODE/static path

#`This code differs from handlers/file.py because files here are not tracked in the DB

from __future__ import with_statement
import time
import re

from twisted.internet import threads
from cyclone.web import os
from twisted.internet.defer import inlineCallbacks

from globaleaks.settings import GLSetting, transact, transact_ro
from globaleaks.handlers.base import BaseHandler
from globaleaks.handlers.authentication import transport_security_check, authenticated
from globaleaks.utils import log
from globaleaks.rest import errors
from globaleaks.rest.base import uuid_regexp
from globaleaks import models

def get_description_by_stat(statstruct, name):
    stored_file_desc =  {
            'filename': name,
            'size': statstruct.st_size,
        }
    return stored_file_desc


def get_stored_files():
    stored_list = []
    storedfiles = os.listdir(GLSetting.static_path)

    for fname in storedfiles:
        filepath = os.path.join(GLSetting.static_path, fname)
        statinfo = os.stat(filepath)
        stored_list.append(get_description_by_stat(statinfo, fname))

    return stored_list


def get_file_info(uploaded_file):
    """
    @param filesinupload: the bulk of Cyclone upload data
    @return: list of files with content_type and size.
    """

    file_desc = {
        'filename': uploaded_file['filename'],
        'content_type': uploaded_file['content_type'],
        'size': uploaded_file['body_len'],
        '_gl_file_path': uploaded_file['_gl_file_path'],
    }

    return file_desc


def dump_static_file(uploaded_file):
    """
    @param files: files uploaded in Cyclone upload
    @return: a relationship dict linking the filename with the random
        filename saved in the disk
    """

    # exceptions of type OSError raised inside this function are handled by handler
    filelocation = uploaded_file['_gl_file_path']

    if os.path.exists(filelocation):
        log.err("Path %s exists and would be overwritten with %d bytes" %
            (filelocation, uploaded_file['body_len'] ) )
    else:
        log.debug("Creating %s with %d bytes" %
            (filelocation, uploaded_file['body_len'] ) )

    with open(filelocation, 'w+') as fd:
        uploaded_file['body'].seek(0, 0)
        data = uploaded_file['body'].read(4000) # 4kb
        while data != "":
            os.write(fd.fileno(), data)
            data = uploaded_file['body'].read(4000) # 4kb

    return get_file_info(uploaded_file)

def reserved_name_check(target_string):
    """
    @param target_string: its a string,

      This function is used for two different reasons:

        1) from the URI query, because if is present and match a reserved
           pattern, than is because Admin want trigger a special behavior
        2) from file upload data, because filename with reserved name need to
           be deny

    @return: True if a match is found, False if not.
    """
    reserved_logo_namel = len(GLSetting.reserved_nodelogo_name)
    if target_string[:reserved_logo_namel] == GLSetting.reserved_nodelogo_name:
        if len(target_string) > reserved_logo_namel:
            raise errors.ReservedFileName
        return True

    # an UUID is long 36 byte
    if re.match(uuid_regexp, target_string[:36]):
        if len(target_string) > 36:
            raise errors.ReservedFileName
        return True

    return False

@transact_ro
def receiver_pic_path(store, receiver_uuid):
    receiver = store.find(models.Receiver, models.Receiver.id == unicode(receiver_uuid)).one()

    if not receiver:
        raise errors.ReceiverGusNotFound

    return os.path.join(GLSetting.static_path, "%s.png" % receiver_uuid)

class StaticFileCollection(BaseHandler):
    """
    Complete CRUD implementation using the filename instead of UUIDs
    """

    @transport_security_check('admin')
    @authenticated('admin')
    @inlineCallbacks
    def post(self, *args):
        """
        Upload a new file
        """
        start_time = time.time()

        uploaded_file = self.request.body

        # currently the static file upload is used to handle only
        # images uploads for Node and for Receivers so that all the logic
        # is embedded here.

        if not uploaded_file['filename'].lower().endswith(GLSetting.supported_extensions):
            raise errors.InvalidInputFormat("file extension not supported")

        if reserved_name_check(uploaded_file['filename']):
            raise errors.ReservedFileName

        # if special meaning is specified, in this case,
        # the original name of the file is changed with the appropriate one.
        if reserved_name_check(self.request.query):
            specified_keyword = self.request.query

            if specified_keyword == GLSetting.reserved_nodelogo_name:
                try:
                    uploaded_file['_gl_file_path'] = os.path.join(GLSetting.static_path, "%s.png" % GLSetting.reserved_nodelogo_name)
                    log.debug("Received request to update Node logo in %s" % uploaded_file['filename'])
                except Exception as excpd:
                    log.err("Exception raised while saving Node logo: %s" % excpd)
                    raise errors.InternalServerError(excpd.__repr__())
            else:
                try:
                    uploaded_file['_gl_file_path'] = yield receiver_pic_path(specified_keyword)
                    log.debug("Received request to update Receiver portrait for %s" % specified_keyword)
                except errors.ReceiverGusNotFound as excpd:
                    log.err("Invalid Receiver ID specified: %s" % specified_keyword)
                    raise excpd
                except Exception as excpd:
                    log.err("Exception raised while saving Receiver %s portrait %s" %
                            (specified_keyword, excpd))
                    raise errors.InternalServerError(excpd.__repr__())

        try:
            # the dump of the file is done here in the latest stage to
            # avoid writing non tracked files on the file system in case of exceptions
            dumped_file = yield threads.deferToThread(dump_static_file, uploaded_file)
        except OSError as excpd:
            inf_list = get_file_info(uploaded_file)
            # I never tried effectively this error
            log.err("OSError while create a new static file [%s]: %s" % (str(inf_list), excpd))
            raise errors.InternalServerError(excpd.strerror)
        except Exception as excpd:
            log.err("Not handled exception: %s" % excpd.__repr__())
            raise errors.InternalServerError(excpd.__repr__())

        dumped_file['elapsed_time'] = time.time() - start_time

        log.debug("Admin uploaded new static file: %s" % dumped_file['filename'])

        self.set_status(201) # Created
        self.finish(dumped_file)


    @transport_security_check('admin')
    @authenticated('admin')
    def get(self, *args):
        """
        Return the list of static files, with few filesystem info
        """
        self.set_status(200)
        self.finish(get_stored_files())


class StaticFileInstance(BaseHandler):
    """
    This interface do not support at the moment GET and PUT, because the only
    useful function in this case is the single deletion.
    """

    @transport_security_check('admin')
    @authenticated('admin')
    def delete(self, filename, *args):
        """
        Parameter: filename
        Errors: StaticFileNotFound
        """
        filelocation = os.path.join(GLSetting.static_path, filename)

        if not os.path.exists(filelocation):
            raise errors.StaticFileNotFound

        # XXX if a reserved filename is requested, need to be handled in
        # a safe way: eg, if is a receiver, restore the default image.
        os.unlink(filelocation)

        self.set_status(200)
        self.finish()
