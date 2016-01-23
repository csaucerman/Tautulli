﻿# This file is part of PlexPy.
#
#  PlexPy is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  PlexPy is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with PlexPy.  If not, see <http://www.gnu.org/licenses/>.

from plexpy import logger, datatables, common, database, helpers
import plexpy

def update_section_ids():
    from plexpy import pmsconnect, activity_pinger
    import threading

    plexpy.CONFIG.UPDATE_SECTION_IDS = -1

    logger.info(u"PlexPy Libraries :: Updating section_id's in database.")

    logger.debug(u"PlexPy Libraries :: Disabling monitoring while update in progress.")
    plexpy.schedule_job(activity_pinger.check_active_sessions, 'Check for active sessions',
                        hours=0, minutes=0, seconds=0)
    plexpy.schedule_job(activity_pinger.check_recently_added, 'Check for recently added items',
                        hours=0, minutes=0, seconds=0)
    plexpy.schedule_job(activity_pinger.check_server_response, 'Check for server response',
                        hours=0, minutes=0, seconds=0)

    monitor_db = database.MonitorDatabase()

    try:
        query = 'SELECT id, rating_key FROM session_history_metadata WHERE section_id IS NULL'
        result = monitor_db.select(query=query)
    except Exception as e:
        logger.warn(u"PlexPy Libraries :: Unable to execute database query for update_section_ids: %s." % e)

        logger.warn(u"PlexPy Libraries :: Unable to update section_id's in database.")
        plexpy.CONFIG.__setattr__('UPDATE_SECTION_IDS', 1)
        plexpy.CONFIG.write()

        logger.debug(u"PlexPy Libraries :: Re-enabling monitoring.")
        plexpy.initialize_scheduler()
        return None

    # Add thread filter to the logger
    logger.debug(u"PlexPy Libraries :: Disabling logging in the current thread while update in progress.")
    thread_filter = logger.NoThreadFilter(threading.current_thread().name)
    for handler in logger.logger.handlers:
        handler.addFilter(thread_filter)

    pms_connect = pmsconnect.PmsConnect()

    error_keys = set()
    for item in result:
        id = item['id']
        rating_key = item['rating_key']
        metadata = pms_connect.get_metadata_details(rating_key=rating_key)

        if metadata:
            metadata = metadata['metadata']
            section_keys = {'id': id}
            section_values = {'section_id': metadata['section_id']}
            monitor_db.upsert('session_history_metadata', key_dict=section_keys, value_dict=section_values)
        else:
            error_keys.add(rating_key)

    # Remove thread filter from the logger
    for handler in logger.logger.handlers:
        handler.removeFilter(thread_filter)
    logger.debug(u"PlexPy Libraries :: Re-enabling logging in the current thread.")

    if error_keys:
        logger.info(u"PlexPy Libraries :: Updated all section_id's in database except for rating_keys: %s." %
                     ', '.join(str(key) for key in error_keys))
    else:
        logger.info(u"PlexPy Libraries :: Updated all section_id's in database.")

    plexpy.CONFIG.__setattr__('UPDATE_SECTION_IDS', 0)
    plexpy.CONFIG.write()

    logger.debug(u"PlexPy Libraries :: Re-enabling monitoring.")
    plexpy.initialize_scheduler()

    return True

class Libraries(object):

    def __init__(self):
        pass

    def get_datatables_list(self, kwargs=None):
        data_tables = datatables.DataTables()

        custom_where = ['library_sections.deleted_section', 0]

        columns = ['library_sections.section_id',
                   'library_sections.section_name',
                   'library_sections.section_type',
                   'library_sections.count',
                   'library_sections.parent_count',
                   'library_sections.child_count',
                   'library_sections.thumb AS library_thumb',
                   'library_sections.custom_thumb_url AS custom_thumb',
                   'library_sections.art',
                   'COUNT(session_history.id) AS plays',
                   'MAX(session_history.started) AS last_accessed',
                   'MAX(session_history.id) AS id',
                   'session_history_metadata.full_title AS last_watched',
                   'session_history_metadata.thumb',
                   'session_history_metadata.parent_thumb',
                   'session_history_metadata.grandparent_thumb',
                   'session_history_metadata.media_type',
                   'session_history.rating_key',
                   'session_history_media_info.video_decision',
                   'library_sections.do_notify',
                   'library_sections.do_notify_created',
                   'library_sections.keep_history'
                   ]
        try:
            query = data_tables.ssp_query(table_name='library_sections',
                                          columns=columns,
                                          custom_where=[custom_where],
                                          group_by=['library_sections.server_id', 'library_sections.section_id'],
                                          join_types=['LEFT OUTER JOIN',
                                                      'LEFT OUTER JOIN',
                                                      'LEFT OUTER JOIN'],
                                          join_tables=['session_history_metadata',
                                                       'session_history',
                                                       'session_history_media_info'],
                                          join_evals=[['session_history_metadata.section_id', 'library_sections.section_id'],
                                                      ['session_history_metadata.id', 'session_history.id'],
                                                      ['session_history_metadata.id', 'session_history_media_info.id']],
                                          kwargs=kwargs)
        except Exception as e:
            logger.warn(u"PlexPy Libraries :: Unable to execute database query for get_list: %s." % e)
            return {'recordsFiltered': 0,
                    'recordsTotal': 0,
                    'draw': 0,
                    'data': 'null',
                    'error': 'Unable to execute database query.'}

        result = query['result']
        
        rows = []
        for item in result:
            if item['media_type'] == 'episode' and item['parent_thumb']:
                thumb = item['parent_thumb']
            elif item['media_type'] == 'episode':
                thumb = item['grandparent_thumb']
            else:
                thumb = item['thumb']

            if item['custom_thumb'] and item['custom_thumb'] != item['library_thumb']:
                library_thumb = item['custom_thumb']
            elif item['library_thumb']:
                library_thumb = item['library_thumb']
            else:
                library_thumb = common.DEFAULT_COVER_THUMB

            row = {'section_id': item['section_id'],
                   'section_name': item['section_name'],
                   'section_type': item['section_type'].capitalize(),
                   'count': item['count'],
                   'parent_count': item['parent_count'],
                   'child_count': item['child_count'],
                   'library_thumb': library_thumb,
                   'library_art': item['art'],
                   'plays': item['plays'],
                   'last_accessed': item['last_accessed'],
                   'id': item['id'],
                   'last_watched': item['last_watched'],
                   'thumb': thumb,
                   'media_type': item['media_type'],
                   'rating_key': item['rating_key'],
                   'video_decision': item['video_decision'],
                   'do_notify': helpers.checked(item['do_notify']),
                   'do_notify_created': helpers.checked(item['do_notify_created']),
                   'keep_history': helpers.checked(item['keep_history'])
                   }

            rows.append(row)
        
        dict = {'recordsFiltered': query['filteredCount'],
                'recordsTotal': query['totalCount'],
                'data': rows,
                'draw': query['draw']
                }
        
        return dict

    def get_datatables_media_info(self, section_id=None, section_type=None, rating_key=None, refresh=False, kwargs=None):
        from plexpy import pmsconnect
        import json, os

        default_return = {'recordsFiltered': 0,
                          'recordsTotal': 0,
                          'draw': 0,
                          'data': None,
                          'error': 'Unable to execute database query.'}

        if section_id and not str(section_id).isdigit():
            logger.warn(u"PlexPy Libraries :: Datatable media info called by invalid section_id provided.")
            return default_return
        elif rating_key and not str(rating_key).isdigit():
            logger.warn(u"PlexPy Libraries :: Datatable media info called by invalid rating_key provided.")
            return default_return

        # Get the library details
        library_details = self.get_details(section_id=section_id)
        if library_details['section_id'] == None:
            logger.debug(u"PlexPy Libraries :: Library section_id %s not found." % section_id)
            return default_return

        if not section_type:
            section_type = library_details['section_type']

        # Get play counts from the database
        monitor_db = database.MonitorDatabase()

        if plexpy.CONFIG.GROUP_HISTORY_TABLES:
            count_by = 'reference_id'
        else:
            count_by = 'id'

        if section_type == 'show' or section_type == 'artist':
            group_by = 'grandparent_rating_key'
        elif section_type == 'season' or section_type == 'album':
            group_by = 'parent_rating_key'
        else:
            group_by = 'rating_key'

        try:
            query = 'SELECT MAX(session_history.started) AS last_watched, COUNT(DISTINCT session_history.%s) AS play_count, ' \
                    'session_history.rating_key, session_history.parent_rating_key, session_history.grandparent_rating_key ' \
                    'FROM session_history ' \
                    'JOIN session_history_metadata ON session_history.id = session_history_metadata.id ' \
                    'WHERE session_history_metadata.section_id = ? ' \
                    'GROUP BY session_history.%s ' % (count_by, group_by)
            result = monitor_db.select(query, args=[section_id])
        except Exception as e:
            logger.warn(u"PlexPy Libraries :: Unable to execute database query for get_datatables_media_info2: %s." % e)
            return default_return

        watched_list = {}
        for item in result:
            watched_list[str(item[group_by])] = {'last_watched': item['last_watched'],
                                                 'play_count': item['play_count']}

        rows = []
        # Import media info cache from json file
        if rating_key:
            try:
                inFilePath = os.path.join(plexpy.CONFIG.CACHE_DIR,'media_info_%s-%s.json' % (section_id, rating_key))
                with open(inFilePath, 'r') as inFile:
                    rows = json.load(inFile)
                    library_count = len(rows)
            except IOError as e:
                #logger.debug(u"PlexPy Libraries :: No JSON file for rating_key %s." % rating_key)
                #logger.debug(u"PlexPy Libraries :: Refreshing data and creating new JSON file for rating_key %s." % rating_key)
                pass
        elif section_id:
            try:
                inFilePath = os.path.join(plexpy.CONFIG.CACHE_DIR,'media_info_%s.json' % section_id)
                with open(inFilePath, 'r') as inFile:
                    rows = json.load(inFile)
                    library_count = len(rows)
            except IOError as e:
                #logger.debug(u"PlexPy Libraries :: No JSON file for library section_id %s." % section_id)
                #logger.debug(u"PlexPy Libraries :: Refreshing data and creating new JSON file for section_id %s." % section_id)
                pass

        # If no cache was imported, get all library children items
        cached_items = {d['rating_key']: d['file_size'] for d in rows}

        if refresh or not rows:
            pms_connect = pmsconnect.PmsConnect()

            if rating_key:
                library_children = pms_connect.get_library_children_details(rating_key=rating_key,
                                                                            get_media_info=True)
            elif section_id:
                library_children = pms_connect.get_library_children_details(section_id=section_id,
                                                                            section_type=section_type,
                                                                            get_media_info=True)
            
            if library_children:
                library_count = library_children['library_count']
                children_list = library_children['childern_list']
            else:
                logger.warn(u"PlexPy Libraries :: Unable to get a list of library items.")
                return default_return
            
            new_rows = []
            for item in children_list:
                cached_file_size = cached_items.get(item['rating_key'], None)
                file_size = cached_file_size if cached_file_size else item.get('file_size', '')

                row = {'section_id': library_details['section_id'],
                       'section_type': library_details['section_type'],
                       'added_at': item['added_at'],
                       'media_type': item['media_type'],
                       'rating_key': item['rating_key'],
                       'parent_rating_key': item['parent_rating_key'],
                       'grandparent_rating_key': item['grandparent_rating_key'],
                       'title': item['title'],
                       'year': item['year'],
                       'media_index': item['media_index'],
                       'parent_media_index': item['parent_media_index'],
                       'thumb': item['thumb'],
                       'container': item.get('container', ''),
                       'bitrate': item.get('bitrate', ''),
                       'video_codec': item.get('video_codec', ''),
                       'video_resolution': item.get('video_resolution', ''),
                       'video_framerate': item.get('video_framerate', ''),
                       'audio_codec': item.get('audio_codec', ''),
                       'audio_channels': item.get('audio_channels', ''),
                       'file_size': file_size
                       }
                new_rows.append(row)

            rows = new_rows
            if not rows:
                return default_return

            # Cache the media info to a json file
            if rating_key:
                try:
                    outFilePath = os.path.join(plexpy.CONFIG.CACHE_DIR,'media_info_%s-%s.json' % (section_id, rating_key))
                    with open(outFilePath, 'w') as outFile:
                        json.dump(rows, outFile)
                except IOError as e:
                    logger.debug(u"PlexPy Libraries :: Unable to create cache file for rating_key %s." % rating_key)
            elif section_id:
                try:
                    outFilePath = os.path.join(plexpy.CONFIG.CACHE_DIR,'media_info_%s.json' % section_id)
                    with open(outFilePath, 'w') as outFile:
                        json.dump(rows, outFile)
                except IOError as e:
                    logger.debug(u"PlexPy Libraries :: Unable to create cache file for section_id %s." % section_id)

        # Update the last_watched and play_count
        for item in rows:
            watched_item = watched_list.get(item['rating_key'], None)
            if watched_item:
                item['last_watched'] = watched_item['last_watched']
                item['play_count'] = watched_item['play_count']
            else:
                item['last_watched'] = None
                item['play_count'] = None

        results = []
        
        # Get datatables JSON data            
        if kwargs.get('json_data'):
            json_data = helpers.process_json_kwargs(json_kwargs=kwargs.get('json_data'))
            #print json_data

        # Search results
        search_value = json_data['search']['value'].lower()
        if search_value:
            searchable_columns = [d['data'] for d in json_data['columns'] if d['searchable']]
            for row in rows:
                for k,v in row.iteritems():
                    if k in searchable_columns and search_value in v.lower():
                        results.append(row)
                        break
        else:
            results = rows

        filtered_count = len(results)

        # Sort results
        results = sorted(results, key=lambda k: k['title'])
        sort_order = json_data['order']
        for order in reversed(sort_order):
            sort_key = json_data['columns'][int(order['column'])]['data']
            reverse = True if order['dir'] == 'desc' else False
            if rating_key and sort_key == 'title':
                results = sorted(results, key=lambda k: helpers.cast_to_int(k['media_index']), reverse=reverse)
            elif sort_key == 'file_size' or sort_key == 'bitrate':
                results = sorted(results, key=lambda k: helpers.cast_to_int(k[sort_key]), reverse=reverse)
            else:
                results = sorted(results, key=lambda k: k[sort_key], reverse=reverse)

        total_file_size = sum([helpers.cast_to_int(d['file_size']) for d in results])

        # Paginate results
        results = results[json_data['start']:(json_data['start'] + json_data['length'])]

        filtered_file_size = sum([helpers.cast_to_int(d['file_size']) for d in results])

        dict = {'recordsFiltered': filtered_count,
                'recordsTotal': library_count,
                'data': results,
                'draw': int(json_data['draw']),
                'filtered_file_size': filtered_file_size,
                'total_file_size': total_file_size
                }
        
        return dict

    def get_media_info_file_sizes(self, section_id=None, rating_key=None):
        from plexpy import pmsconnect
        import json, os

        if section_id and not str(section_id).isdigit():
            logger.warn(u"PlexPy Libraries :: Datatable media info file size called by invalid section_id provided.")
            return False
        elif rating_key and not str(rating_key).isdigit():
            logger.warn(u"PlexPy Libraries :: Datatable media info file size called by invalid rating_key provided.")
            return False

        # Get the library details
        library_details = self.get_details(section_id=section_id)
        if library_details['section_id'] == None:
            logger.debug(u"PlexPy Libraries :: Library section_id %s not found." % section_id)
            return False
        if library_details['section_type'] == 'photo':
            return False

        rows = []
        # Import media info cache from json file
        if rating_key:
            #logger.debug(u"PlexPy Libraries :: Getting file sizes for rating_key %s." % rating_key)
            try:
                inFilePath = os.path.join(plexpy.CONFIG.CACHE_DIR,'media_info_%s-%s.json' % (section_id, rating_key))
                with open(inFilePath, 'r') as inFile:
                    rows = json.load(inFile)
            except IOError as e:
                #logger.debug(u"PlexPy Libraries :: No JSON file for rating_key %s." % rating_key)
                #logger.debug(u"PlexPy Libraries :: Refreshing data and creating new JSON file for rating_key %s." % rating_key)
                pass
        elif section_id:
            logger.debug(u"PlexPy Libraries :: Getting file sizes for section_id %s." % section_id)
            try:
                inFilePath = os.path.join(plexpy.CONFIG.CACHE_DIR,'media_info_%s.json' % section_id)
                with open(inFilePath, 'r') as inFile:
                    rows = json.load(inFile)
            except IOError as e:
                #logger.debug(u"PlexPy Libraries :: No JSON file for library section_id %s." % section_id)
                #logger.debug(u"PlexPy Libraries :: Refreshing data and creating new JSON file for section_id %s." % section_id)
                pass

        # Get the total file size for each item
        pms_connect = pmsconnect.PmsConnect()

        for item in rows:
            if item['rating_key'] and not item['file_size']:
                file_size = 0
            
                child_metadata = pms_connect.get_metadata_children_details(rating_key=item['rating_key'],
                                                                           get_children=True,
                                                                           get_media_info=True)
                metadata_list = child_metadata['metadata']

                for child_metadata in metadata_list:
                    file_size += helpers.cast_to_int(child_metadata.get('file_size', 0))

                item['file_size'] = file_size

        # Cache the media info to a json file
        if rating_key:
            try:
                outFilePath = os.path.join(plexpy.CONFIG.CACHE_DIR,'media_info_%s-%s.json' % (section_id, rating_key))
                with open(outFilePath, 'w') as outFile:
                    json.dump(rows, outFile)
            except IOError as e:
                logger.debug(u"PlexPy Libraries :: Unable to create cache file with file sizes for rating_key %s." % rating_key)
        elif section_id:
            try:
                outFilePath = os.path.join(plexpy.CONFIG.CACHE_DIR,'media_info_%s.json' % section_id)
                with open(outFilePath, 'w') as outFile:
                    json.dump(rows, outFile)
            except IOError as e:
                logger.debug(u"PlexPy Libraries :: Unable to create cache file with file sizes for section_id %s." % section_id)

        if rating_key:
            #logger.debug(u"PlexPy Libraries :: File sizes updated for rating_key %s." % rating_key)
            pass
        elif section_id:
            logger.debug(u"PlexPy Libraries :: File sizes updated for section_id %s." % section_id)

        return True
    
    def set_config(self, section_id=None, custom_thumb='', do_notify=1, keep_history=1, do_notify_created=1):
        if section_id:
            monitor_db = database.MonitorDatabase()

            key_dict = {'section_id': section_id}
            value_dict = {'custom_thumb_url': custom_thumb,
                          'do_notify': do_notify,
                          'do_notify_created': do_notify_created,
                          'keep_history': keep_history}
            try:
                monitor_db.upsert('library_sections', value_dict, key_dict)
            except:
                logger.warn(u"PlexPy Libraries :: Unable to execute database query for set_config: %s." % e)

    def get_details(self, section_id=None):
        from plexpy import pmsconnect

        monitor_db = database.MonitorDatabase()

        try:
            if section_id:
                query = 'SELECT section_id, section_name, section_type, count, parent_count, child_count, ' \
                        'thumb AS library_thumb, custom_thumb_url AS custom_thumb, art, ' \
                        'do_notify, do_notify_created, keep_history ' \
                        'FROM library_sections ' \
                        'WHERE section_id = ? '
                result = monitor_db.select(query, args=[section_id])
            else:
                result = []
        except Exception as e:
            logger.warn(u"PlexPy Libraries :: Unable to execute database query for get_details: %s." % e)
            result = []

        if result:
            library_details = {}
            for item in result:
                if item['custom_thumb'] and item['custom_thumb'] != item['library_thumb']:
                    library_thumb = item['custom_thumb']
                elif item['library_thumb']:
                    library_thumb = item['library_thumb']
                else:
                    library_thumb = common.DEFAULT_COVER_THUMB

                library_details = {'section_id': item['section_id'],
                                   'section_name': item['section_name'],
                                   'section_type': item['section_type'],
                                   'library_thumb': library_thumb,
                                   'library_art': item['art'],
                                   'count': item['count'],
                                   'parent_count': item['parent_count'],
                                   'child_count': item['child_count'],
                                   'do_notify': item['do_notify'],
                                   'do_notify_created': item['do_notify_created'],
                                   'keep_history': item['keep_history']
                                   }
            return library_details
        else:
            logger.warn(u"PlexPy Libraries :: Unable to retrieve library from local database. Requesting library list refresh.")
            # Let's first refresh the user list to make sure the user isn't newly added and not in the db yet
            try:
                if section_id:
                    # Refresh libraries
                    pmsconnect.refresh_libraries()
                    query = 'SELECT section_id, section_name, section_type, count, parent_count, child_count, ' \
                            'thumb AS library_thumb, custom_thumb_url AS custom_thumb, art, ' \
                            'do_notify, do_notify_created, keep_history ' \
                            'FROM library_sections ' \
                            'WHERE section_id = ? '
                    result = monitor_db.select(query, args=[section_id])
                else:
                    result = []
            except:
                logger.warn(u"PlexPy Libraries :: Unable to execute database query for get_details: %s." % e)
                result = []

            if result:
                library_details = {}
                for item in result:
                    if item['custom_thumb'] and item['custom_thumb'] != item['library_thumb']:
                        library_thumb = item['custom_thumb']
                    elif item['library_thumb']:
                        library_thumb = item['library_thumb']
                    else:
                        library_thumb = common.DEFAULT_COVER_THUMB

                    library_details = {'section_id': item['section_id'],
                                       'section_name': item['section_name'],
                                       'section_type': item['section_type'],
                                       'library_thumb': library_thumb,
                                       'library_art': item['art'],
                                       'count': item['count'],
                                       'parent_count': item['parent_count'],
                                       'child_count': item['child_count'],
                                       'do_notify': item['do_notify'],
                                       'do_notify_created': item['do_notify_created'],
                                       'keep_history': item['keep_history']
                                       }
                return library_details
            else:
                # If there is no library data we must return something
                # Use "Local" user to retain compatibility with PlexWatch database value
                return {'section_id': None,
                        'section_name': 'Local',
                        'section_type': '',
                        'library_thumb': common.DEFAULT_COVER_THUMB,
                        'library_art': '',
                        'count': 0,
                        'parent_count': 0,
                        'child_count': 0,
                        'do_notify': 0,
                        'do_notify_created': 0,
                        'keep_history': 0
                        }

    def get_watch_time_stats(self, section_id=None):
        monitor_db = database.MonitorDatabase()

        time_queries = [1, 7, 30, 0]
        library_watch_time_stats = []

        for days in time_queries:
            try:
                if days > 0:
                    if str(section_id).isdigit():
                        query = 'SELECT (SUM(stopped - started) - ' \
                                'SUM(CASE WHEN paused_counter is null THEN 0 ELSE paused_counter END)) as total_time, ' \
                                'COUNT(session_history.id) AS total_plays ' \
                                'FROM session_history ' \
                                'JOIN session_history_metadata ON session_history_metadata.id = session_history.id ' \
                                'WHERE datetime(stopped, "unixepoch", "localtime") >= datetime("now", "-%s days", "localtime") ' \
                                'AND section_id = ?' % days
                        result = monitor_db.select(query, args=[section_id])
                    else:
                        result = []
                else:
                    if str(section_id).isdigit():
                        query = 'SELECT (SUM(stopped - started) - ' \
                                'SUM(CASE WHEN paused_counter is null THEN 0 ELSE paused_counter END)) as total_time, ' \
                                'COUNT(session_history.id) AS total_plays ' \
                                'FROM session_history ' \
                                'JOIN session_history_metadata ON session_history_metadata.id = session_history.id ' \
                                'WHERE section_id = ?'
                        result = monitor_db.select(query, args=[section_id])
                    else:
                        result = []
            except Exception as e:
                logger.warn(u"PlexPy Libraries :: Unable to execute database query for get_watch_time_stats: %s." % e)
                result = []

            for item in result:
                if item['total_time']:
                    total_time = item['total_time']
                    total_plays = item['total_plays']
                else:
                    total_time = 0
                    total_plays = 0

                row = {'query_days': days,
                       'total_time': total_time,
                       'total_plays': total_plays
                       }

                library_watch_time_stats.append(row)

        return library_watch_time_stats

    def get_user_stats(self, section_id=None):
        monitor_db = database.MonitorDatabase()

        user_stats = []

        try:
            if str(section_id).isdigit():
                query = 'SELECT (CASE WHEN users.friendly_name IS NULL THEN users.username ' \
                        'ELSE users.friendly_name END) AS user, users.user_id, users.thumb, COUNT(user) AS user_count ' \
                        'FROM session_history ' \
                        'JOIN session_history_metadata ON session_history_metadata.id = session_history.id ' \
                        'JOIN users ON users.user_id = session_history.user_id ' \
                        'WHERE section_id = ? ' \
                        'GROUP BY users.user_id ' \
                        'ORDER BY user_count DESC'
                result = monitor_db.select(query, args=[section_id])
            else:
                result = []
        except Exception as e:
            logger.warn(u"PlexPy Libraries :: Unable to execute database query for get_user_stats: %s." % e)
            result = []
        
        for item in result:
            row = {'user': item['user'],
                   'user_id': item['user_id'],
                   'thumb': item['thumb'],
                   'total_plays': item['user_count']
                   }
            user_stats.append(row)
        
        return user_stats

    def get_recently_watched(self, section_id=None, limit='10'):
        monitor_db = database.MonitorDatabase()
        recently_watched = []

        if not limit.isdigit():
            limit = '10'

        try:
            if str(section_id).isdigit():
                query = 'SELECT session_history.id, session_history.media_type, session_history.rating_key, session_history.parent_rating_key, ' \
                        'title, parent_title, grandparent_title, thumb, parent_thumb, grandparent_thumb, media_index, parent_media_index, ' \
                        'year, started, user ' \
                        'FROM session_history_metadata ' \
                        'JOIN session_history ON session_history_metadata.id = session_history.id ' \
                        'WHERE section_id = ? ' \
                        'GROUP BY (CASE WHEN session_history.media_type = "track" THEN session_history.parent_rating_key ' \
                        '   ELSE session_history.rating_key END) ' \
                        'ORDER BY started DESC LIMIT ?'
                result = monitor_db.select(query, args=[section_id, limit])
            else:
                result = []
        except Exception as e:
            logger.warn(u"PlexPy Libraries :: Unable to execute database query for get_recently_watched: %s." % e)
            result = []

        for row in result:
                if row['media_type'] == 'episode' and row['parent_thumb']:
                    thumb = row['parent_thumb']
                elif row['media_type'] == 'episode':
                    thumb = row['grandparent_thumb']
                else:
                    thumb = row['thumb']

                recent_output = {'row_id': row['id'],
                                 'media_type': row['media_type'],
                                 'rating_key': row['rating_key'],
                                 'title': row['title'],
                                 'parent_title': row['parent_title'],
                                 'grandparent_title': row['grandparent_title'],
                                 'thumb': thumb,
                                 'media_index': row['media_index'],
                                 'parent_media_index': row['parent_media_index'],
                                 'year': row['year'],
                                 'time': row['started'],
                                 'user': row['user']
                                 }
                recently_watched.append(recent_output)

        return recently_watched

    def get_sections(self):
        monitor_db = database.MonitorDatabase()

        try:
            query = 'SELECT section_id, section_name FROM library_sections WHERE deleted_section = 0'
            result = monitor_db.select(query=query)
        except Exception as e:
            logger.warn(u"PlexPy Libraries :: Unable to execute database query for get_sections: %s." % e)
            return None

        libraries = []
        for item in result:
            library = {'section_id': item['section_id'],
                       'section_name': item['section_name']
                       }
            libraries.append(library)

        return libraries

    def delete_all_history(self, section_id=None):
        monitor_db = database.MonitorDatabase()

        try:
            if section_id.isdigit():
                logger.info(u"PlexPy Libraries :: Deleting all history for library id %s from database." % section_id)
                session_history_media_info_del = \
                    monitor_db.action('DELETE FROM '
                                      'session_history_media_info '
                                      'WHERE session_history_media_info.id IN (SELECT session_history_media_info.id '
                                      'FROM session_history_media_info '
                                      'JOIN session_history_metadata ON session_history_media_info.id = session_history_metadata.id '
                                      'WHERE session_history_metadata.section_id = ?)', [section_id])
                session_history_del = \
                    monitor_db.action('DELETE FROM '
                                      'session_history '
                                      'WHERE session_history.id IN (SELECT session_history.id '
                                      'FROM session_history '
                                      'JOIN session_history_metadata ON session_history.id = session_history_metadata.id '
                                      'WHERE session_history_metadata.section_id = ?)', [section_id])
                session_history_metadata_del = \
                    monitor_db.action('DELETE FROM '
                                      'session_history_metadata '
                                      'WHERE session_history_metadata.section_id = ?', [section_id])

                return 'Deleted all items for section_id %s.' % section_id
            else:
                return 'Unable to delete items, section_id not valid.'
        except Exception as e:
            logger.warn(u"PlexPy Libraries :: Unable to execute database query for delete_all_history: %s." % e)

    def delete(self, section_id=None):
        monitor_db = database.MonitorDatabase()

        try:
            if section_id.isdigit():
                self.delete_all_history(section_id)
                logger.info(u"PlexPy Libraries :: Deleting library with id %s from database." % section_id)
                monitor_db.action('UPDATE library_sections SET deleted_section = 1 WHERE section_id = ?', [section_id])
                monitor_db.action('UPDATE library_sections SET keep_history = 0 WHERE section_id = ?', [section_id])
                monitor_db.action('UPDATE library_sections SET do_notify = 0 WHERE section_id = ?', [section_id])
                monitor_db.action('UPDATE library_sections SET do_notify_created = 0 WHERE section_id = ?', [section_id])

                library_cards = plexpy.CONFIG.HOME_LIBRARY_CARDS
                if section_id in library_cards:
                    library_cards.remove(section_id)
                    plexpy.CONFIG.__setattr__('HOME_LIBRARY_CARDS', library_cards)
                    plexpy.CONFIG.write()

                return 'Deleted library with id %s.' % section_id
            else:
                return 'Unable to delete library, section_id not valid.'
        except Exception as e:
            logger.warn(u"PlexPy Libraries :: Unable to execute database query for delete: %s." % e)

    def undelete(self, section_id=None, section_name=None):
        monitor_db = database.MonitorDatabase()

        try:
            if section_id and section_id.isdigit():
                logger.info(u"PlexPy Libraries :: Re-adding library with id %s to database." % section_id)
                monitor_db.action('UPDATE library_sections SET deleted_section = 0 WHERE section_id = ?', [section_id])
                monitor_db.action('UPDATE library_sections SET keep_history = 1 WHERE section_id = ?', [section_id])
                monitor_db.action('UPDATE library_sections SET do_notify = 1 WHERE section_id = ?', [section_id])
                monitor_db.action('UPDATE library_sections SET do_notify_created = 1 WHERE section_id = ?', [section_id])

                return 'Re-added library with id %s.' % section_id
            elif section_name:
                logger.info(u"PlexPy Libraries :: Re-adding library with name %s to database." % section_name)
                monitor_db.action('UPDATE library_sections SET deleted_section = 0 WHERE section_name = ?', [section_name])
                monitor_db.action('UPDATE library_sections SET keep_history = 1 WHERE section_name = ?', [section_name])
                monitor_db.action('UPDATE library_sections SET do_notify = 1 WHERE section_name = ?', [section_name])
                monitor_db.action('UPDATE library_sections SET do_notify_created = 1 WHERE section_name = ?', [section_name])

                return 'Re-added library with section_name %s.' % section_name
            else:
                return 'Unable to re-add library, section_id or section_name not valid.'
        except Exception as e:
            logger.warn(u"PlexPy Libraries :: Unable to execute database query for undelete: %s." % e)

    def delete_datatable_media_info_cache(self, section_id=None):
        import os

        try:
            if section_id.isdigit():
                [os.remove(os.path.join(plexpy.CONFIG.CACHE_DIR, f)) for f in os.listdir(plexpy.CONFIG.CACHE_DIR) 
                 if f.startswith('media_info-%s' % section_id) and f.endswith('.json')]

                logger.debug(u"PlexPy Libraries :: Deleted media info table cache for section_id %s." % section_id)
                return 'Deleted media info table cache for library with id %s.' % section_id
            else:
                return 'Unable to delete media info table cache, section_id not valid.'
        except Exception as e:
            logger.warn(u"PlexPy Libraries :: Unable to delete media info table cache: %s." % e)